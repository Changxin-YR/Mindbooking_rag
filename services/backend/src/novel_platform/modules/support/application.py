from uuid import uuid4

from novel_platform.modules.support.domain import (
    SupportMessage,
    SupportPriority,
    SupportStatus,
    SupportTicket,
)


class SupportService:
    def __init__(self) -> None:
        self._tickets: dict[str, SupportTicket] = {}

    def open_ticket(
        self, account_id: str, category: str, priority: SupportPriority, description: str = ""
    ) -> SupportTicket:
        ticket = SupportTicket(
            id=f"TKT_{uuid4().hex}", account_id=account_id, category=category, priority=priority
        )
        if description:
            ticket.messages.append(
                SupportMessage(
                    id=f"MSG_{uuid4().hex}", ticket_id=ticket.id, author="USER", body=description
                )
            )
        self._tickets[ticket.id] = ticket
        return ticket

    def get_ticket(self, ticket_id: str) -> SupportTicket:
        return self._tickets[ticket_id]

    def list_tickets(self, account_id: str) -> list[SupportTicket]:
        return [ticket for ticket in self._tickets.values() if ticket.account_id == account_id]

    def resolve(self, ticket_id: str) -> SupportTicket:
        ticket = self.get_ticket(ticket_id)
        if ticket.status is SupportStatus.CLOSED:
            raise ValueError("closed ticket cannot be resolved")
        ticket.status = SupportStatus.RESOLVED
        return ticket

    def reply(self, ticket_id: str, body: str, author: str) -> SupportMessage:
        ticket = self.get_ticket(ticket_id)
        message = SupportMessage(
            id=f"MSG_{uuid4().hex}", ticket_id=ticket.id, author=author, body=body
        )
        ticket.messages.append(message)
        if author == "USER" and ticket.status is SupportStatus.RESOLVED:
            ticket.status = SupportStatus.IN_PROGRESS
        return message

    def modify_asset(self, account_id: str, asset_type: str, amount: int) -> None:
        raise PermissionError("support cannot modify assets")
