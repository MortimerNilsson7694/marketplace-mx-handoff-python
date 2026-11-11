import pytest

from marketplace_mail import MailExchanger, MarketplaceOrder, prepare_handoff


def test_priority_order_and_buyer_handoff():
    class RecordingClient:
        def __init__(self):
            self.calls = []

        def request(self, method, path, *, query=None, body=None):
            self.calls.append((method, path, query, body))
            if path == "/v1/dns/domain/get":
                return {"zone_id": "zone-42"}
            if path == "/v1/email/domain/list":
                return {"domains": ["seller.example"]}
            return body

    client = RecordingClient()
    order = MarketplaceOrder("seller.example", "creator-7", ["https://seller.example/a"],
                             "buyer@example.org", "order-19",
                             [MailExchanger("backup.mail.example", 20),
                              MailExchanger("primary.mail.example", 10)])
    result = prepare_handoff(client, order)

    assert client.calls[0] == ("GET", "/v1/dns/domain/get", {"domain": "seller.example"}, None)
    assert [(call[3]["content"], call[3]["priority"]) for call in client.calls[1:3]] == [
        ("primary.mail.example", 10), ("backup.mail.example", 20)]
    assert all(call[3]["zone_id"] == "zone-42" for call in client.calls[1:3])
    assert client.calls[3][1] == "/v1/email/domain/list"
    assert result["buyer_update"]["status"] == "prepared"
    assert result["seller_handoff"]["asset_urls"] == ["https://seller.example/a"]


def test_duplicate_priority_is_rejected_before_writing():
    with pytest.raises(ValueError, match="distinct"):
        MarketplaceOrder("seller.example", "creator-7", ["asset"], "buyer@example.org",
                         "order-19", [MailExchanger("mx1.example", 10),
                                      MailExchanger("mx2.example", 10)])
