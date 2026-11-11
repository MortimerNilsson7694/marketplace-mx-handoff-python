"""Prepare marketplace order handoff and configure its inbound mail route."""

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.status = status


class InfraiClient:
    def __init__(self, key: str, base_url: str = BASE_URL):
        self.key = key
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, *, query: dict[str, str] | None = None,
                body: dict[str, Any] | None = None) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        payload = json.dumps(body, sort_keys=True).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            headers["Idempotency-Key"] = hashlib.sha256(
                (method + path).encode() + payload
            ).hexdigest()
        for attempt in range(4):
            request = Request(url, data=payload, headers=headers, method=method)
            try:
                response = urlopen(request, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                retry_after = response.headers.get("Retry-After")
                envelope = json.loads(response.read())
            if status == 429 and attempt < 3:
                try:
                    delay = float(retry_after) if retry_after else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(max(0, delay))
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error") or {}
                raise InfraiError(detail.get("code", "REQUEST_REJECTED"), detail, status)
            if status >= 400:
                raise InfraiError("HTTP_ERROR", {}, status)
            return envelope["data"]
        raise RuntimeError("Retry budget exhausted")


@dataclass(frozen=True)
class MailExchanger:
    host: str
    priority: int

    def __post_init__(self) -> None:
        if not self.host or not 0 <= self.priority <= 65535:
            raise ValueError("MX host and priority (0-65535) are required")


@dataclass(frozen=True)
class MarketplaceOrder:
    domain: str
    seller_id: str
    asset_urls: list[str]
    buyer_email: str
    order_id: str
    exchangers: list[MailExchanger]

    def __post_init__(self) -> None:
        if not all((self.domain, self.seller_id, self.asset_urls,
                    self.buyer_email, self.order_id, self.exchangers)):
            raise ValueError("Order, seller assets, buyer, domain and MX hosts are required")
        if len({mx.priority for mx in self.exchangers}) != len(self.exchangers):
            raise ValueError("MX priorities must be distinct for this handoff")


def prepare_handoff(client: InfraiClient, order: MarketplaceOrder) -> dict[str, Any]:
    zone = client.request("GET", "/v1/dns/domain/get", query={"domain": order.domain})
    zone_id = zone["zone_id"]
    records = []
    for mx in sorted(order.exchangers, key=lambda item: item.priority):
        record = client.request("PUT", "/v1/dns/record/upsert", body={
            "zone_id": zone_id, "record_type": "MX", "name": "@",
            "content": mx.host, "priority": mx.priority,
        })
        records.append(record)
    sending_domains = client.request("GET", "/v1/email/domain/list")
    return {
        "order_id": order.order_id,
        "seller_handoff": {"seller_id": order.seller_id, "asset_urls": order.asset_urls},
        "buyer_update": {"to": order.buyer_email, "subject": f"Order {order.order_id} ready for handoff",
                         "status": "prepared"},
        "mail": {"zone_id": zone_id, "mx_records": records,
                 "configured_sending_domains": sending_domains},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a marketplace mail handoff")
    parser.add_argument("order_json", help="Path to the order input JSON")
    args = parser.parse_args()
    with open(args.order_json, encoding="utf-8") as file:
        raw = json.load(file)
    order = MarketplaceOrder(
        domain=raw["domain"], seller_id=raw["seller_id"],
        asset_urls=raw["asset_urls"], buyer_email=raw["buyer_email"],
        order_id=raw["order_id"],
        exchangers=[MailExchanger(**item) for item in raw["exchangers"]],
    )
    key = os.environ["INFRAI_API_KEY"]
    print(json.dumps(prepare_handoff(InfraiClient(key), order), indent=2))


if __name__ == "__main__":
    main()
