from pretty_cron import prettify_cron
from casepro.cases.models import Case
from casepro.pods import Pod, PodConfig, PodPlugin
from confmodel import fields
from demands import HTTPServiceError
from seed_services_client.stage_based_messaging \
    import StageBasedMessagingApiClient


class SubscriptionPodConfig(PodConfig):
    url = fields.ConfigText("URL to query for the registration data",
                            required=True)
    token = fields.ConfigText("Authentication token for registration endpoint",
                              required=True)


class SubscriptionPod(Pod):
    def __init__(self, pod_type, config):
        super(SubscriptionPod, self).__init__(pod_type, config)
        url = self.config.url
        token = self.config.token

        # Start a session with the StageBasedMessagingApiClient
        self.stage_based_messaging_api = StageBasedMessagingApiClient(
            token, url)

    def read_data(self, params):
        # Get contact idenity
        case_id = params["case_id"]
        case = Case.objects.get(pk=case_id)
        params = {
            'identity': case.contact.uuid
        }

        try:
            response = self.stage_based_messaging_api.get_subscriptions(params)
        except HTTPServiceError as e:
            return {"items": [{"name": "Error", "value": e.details["detail"]}]}

        # Format and return data
        if response['count'] < 1:
            return {"items": [{"name": "No subscriptions", "value": ""}]}
        data = response["results"]
        content = {"items": []}
        active_sub_ids = []
        for subscription in data:
            subscription_data = {"rows": []}
            # Add the messageset
            message_set_id = subscription['messageset']
            message_set = self.stage_based_messaging_api.get_messageset(
                message_set_id)
            if message_set:
                subscription_data['rows'].append({
                    "name": "Message Set", "value": message_set["short_name"]})
            # Add the sequence number
            subscription_data['rows'].append({
                "name": "Next Sequence Number",
                "value": subscription['next_sequence_number']})
            # Add the schedule
            schedule_id = subscription['schedule']
            schedule = self.stage_based_messaging_api.get_schedule(schedule_id)
            subscription_data['rows'].append({
                "name": "Schedule",
                "value": self.format_schedule(schedule)})
            # Add the active flag
            subscription_data['rows'].append({
                "name": "Active",
                "value": subscription['active']})
            if subscription['active']:
                active_sub_ids.append(subscription['id'])
            # Add the completed flag
            subscription_data['rows'].append({
                "name": "Completed",
                "value": subscription['completed']})
            content['items'].append(subscription_data)

        actions = []
        if len(active_sub_ids) > 0:
            cancel_action = {
                'type': 'cancel_subs',
                'name': 'Cancel All Subscriptions',
                'confirm': True,
                'busy_text': 'Cancelling...',
                'payload': {
                    'subscription_ids': active_sub_ids
                }
            }
            actions.append(cancel_action)

        content['actions'] = actions
        return content

    def format_schedule(self, schedule):
        cron_schedule = "%s %s %s %s %s" % (
            schedule['minute'], schedule['hour'], schedule['day_of_month'],
            schedule['month_of_year'], schedule['day_of_week'])
        return prettify_cron(cron_schedule)

    def perform_action(self, type_, params):
        if type_ == "cancel_subs":
            subscription_ids = params.get("subscription_ids", [])
            params = {'active': False}
            for subscription in subscription_ids:
                try:
                    self.stage_based_messaging_api.update_subscription(
                        subscription, params)
                except HTTPServiceError:
                    return (False,
                            {"message": "Failed to cancel some subscriptions"})
            return (True, {"message": "cancelled all subscriptions"})


class SubscriptionPlugin(PodPlugin):
    name = 'casepropods.family_connect_subscription'
    label = 'family_connect_subscription_pod'
    pod_class = SubscriptionPod
    config_class = SubscriptionPodConfig
    title = 'Subscription Pod'
    directive = 'subscription-pod'
    scripts = ['subscription_pod_directives.js']
    styles = ['subscription_pod.css']
