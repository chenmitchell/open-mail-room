# Intranet install (self-signed certificate)

For an office LAN with no public domain. Everything still needs to be served
over HTTPS — phone browsers refuse camera access on an insecure origin, and the
camera is the primary way parcels get registered. "We're only on the LAN, HTTP
is fine" is the assumption that ends with a camera page that does nothing and
nobody knowing why.

## Generate the certificate

```bash
cd open-mail-room/deploy
chmod +x selfsigned.sh
./selfsigned.sh mailroom.internal 365     # hostname, validity in days
```

Writes `ssl/private.key` (chmod 600) and `ssl/cert.pem`.

Use the hostname staff will actually type. A certificate for `localhost` is
useless to every phone on the network.

## Deploy without a public domain

```bash
./deploy.sh      # no DOMAIN -> no automatic HTTPS via Caddy
```

Point the Caddy config at the generated cert; see `deploy/Caddyfile`.

## The part that will actually bite

Every device gets a browser warning until the certificate is trusted. Untrained
staff click through security warnings, which is a habit worth not teaching them.

Options, best first:

1. **Internal CA / MDM push.** If the org has device management, distribute the
   cert as trusted. Warning disappears, nobody learns to ignore warnings.
2. **Manual trust per device.** Fine for 5 phones, miserable for 50, and it
   resets when the cert expires.
3. **A real certificate on an internal domain.** If they own a domain, a
   DNS-01 challenge issues a real cert for `mailroom.internal.example.com` even
   though the host is unreachable from the internet. Best of both — worth
   raising if they own any domain at all, because it eliminates this whole
   section.

## Expiry

`./selfsigned.sh` defaults to 365 days. Nothing warns you. Put a calendar
reminder in at install time — a year from now, "the mailroom stopped working"
will not obviously mean "the certificate expired", and whoever is on the other
end of that call may not be the person reading this.

Regenerate and restart:

```bash
./selfsigned.sh mailroom.internal 365
docker compose restart
```

## DNS

Staff need `mailroom.internal` to resolve. Internal DNS record, or the router's
local DNS. Handing out an IP address instead works but breaks the certificate
(it's issued for the hostname), so the warning comes back.
