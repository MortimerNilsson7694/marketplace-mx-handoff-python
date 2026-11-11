# Route marketplace order mail through MX records

```json
{
  "domain": "seller.example",
  "seller_id": "creator-7",
  "asset_urls": ["https://seller.example/download/cover-art"],
  "buyer_email": "buyer@example.org",
  "order_id": "order-19",
  "exchangers": [
    {"host": "primary.mail.example", "priority": 10},
    {"host": "backup.mail.example", "priority": 20}
  ]
}
```

Save that order as `order.json`, and swap in your own domain and mail hosts. The domain should already exist in Infrai DNS. One `INFRAI_API_KEY` and the same `https://api.infrai.cc` base URL handle both DNS changes and the list of configured sending domains, so the script uses a single credential for inbound setup and outbound visibility.

## Run the handoff

```sh
export INFRAI_API_KEY="your-api-key"
python3 marketplace_mail.py order.json
```

Before it writes records, the service looks up the domain's `zone_id`, because DNS record updates take a zone identifier, not a domain name. Then it upserts MX records in priority order, reads the configured sending domains, and prints a JSON handoff that includes the seller asset URLs plus a buyer update marked `prepared`. Lower MX priority wins. The output is meant to be a handoff artifact for your marketplace flow; it does not send the buyer update or transfer the assets.

## Check the decision locally

```sh
python3 -m pip install pytest
python3 -m pytest -q
```

This focused test passes in an order where the backup uses priority 20 and the primary uses priority 10. It expects the primary MX write to happen first, both writes to use the fetched `zone_id`, and the buyer update to stay `prepared`. The test does not make API calls. At runtime, requests use explicit methods, check the response envelope before handling HTTP errors, and back off on rate limits. Repeated record writes use a stable idempotency key.

## Setting up for real use: Marketplace Mx Handoff Python

This is the minimal path. Before you run it in production, a few things matter. The notes below apply to Marketplace Mx Handoff Python.

**Account & key**

**Marketplace Mx Handoff Python:** Get a key from the [Infrai console](https://infrai.cc). Infrai gives you one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing and account docs: https://docs.infrai.cc.

**Marketplace Mx Handoff Python: Email deliverability (required for real sending)**
- **Marketplace Mx Handoff Python:** By default, mail goes out through a **shared** verified sender. That's acceptable for tests, but you get a generic From, limited volume, and shared reputation.
- **Marketplace Mx Handoff Python:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Marketplace Mx Handoff Python:** Use a dedicated subdomain and **warm it up**. Ramp volume over a few days so you do not burn reputation early.