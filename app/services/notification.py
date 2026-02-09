import logging

logger = logging.getLogger(__name__)

NOTIFICATION_CHANNELS = ["email", "slack", "webhook"]


class NotificationService:
    def __init__(self, channel="email"):
        self.channel = channel
        self.enabled = False
        self._queue = []

    def send(self, recipient, subject, body):
        if not self.enabled:
            logger.debug(f"Notifications disabled, skipping: {subject}")
            return False
        self._queue.append({
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "channel": self.channel,
        })
        return True

    def send_task_assigned(self, task, assignee):
        return self.send(
            recipient=assignee.email,
            subject=f"Task assigned: {task.title}",
            body=f"You have been assigned to task #{task.id}: {task.title}",
        )

    def send_task_overdue(self, task, assignee):
        return self.send(
            recipient=assignee.email,
            subject=f"Task overdue: {task.title}",
            body=f"Task #{task.id} is past its due date",
        )

    def flush(self):
        count = len(self._queue)
        self._queue.clear()
        return count


notification_service = NotificationService()
