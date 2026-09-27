# Deploying AZone

AZone runs as four containers: the app (wger + the coach, built from this repository), PostgreSQL,
Redis and nginx. Any machine with Docker works. The simplest setup is a small VPS (1 vCPU, 2 GB RAM
is plenty, e.g. Hetzner CX22 or a DigitalOcean basic droplet, about $5 a month).

## 1. First start

On the server (Docker with the compose plugin installed):

```bash
git clone https://github.com/<you>/AZone.git && cd AZone
cp deploy/.env.example deploy/.env
nano deploy/.env        # SITE_URL, CSRF_TRUSTED_ORIGINS, SECRET_KEY, DJANGO_DB_PASSWORD, TIME_ZONE
docker compose -f deploy/docker-compose.yml up -d --build
```

To log in from wger's mobile app too, generate the token keys once and add both lines it prints
to `deploy/.env` (see the comment there):
`docker compose -f deploy/docker-compose.yml run --rm web python3 manage.py generate-jwt-keys`.

The first start takes a few minutes: it builds the image, creates the database and loads the
exercise library. Follow it with `docker compose -f deploy/docker-compose.yml logs -f web`.
The site is then on port 80 (or `AZONE_PORT`).

**Change the admin password right away.** Setup creates a user `admin` with password `adminadmin`.
Log in and change it under your account settings, or run:

```bash
docker compose -f deploy/docker-compose.yml exec web python3 manage.py changepassword admin
```

## 2. HTTPS

Put a TLS proxy in front of nginx. With [Caddy](https://caddyserver.com) on the same server, set
`AZONE_PORT=8080` in `deploy/.env` and use this `Caddyfile`:

```
azone.example.com {
    reverse_proxy localhost:8080
}
```

Caddy gets and renews the certificate by itself. Then set, in `deploy/.env`:

```
SITE_URL=https://azone.example.com
CSRF_TRUSTED_ORIGINS=https://azone.example.com
X_FORWARDED_PROTO_HEADER_SET=True
NUMBER_OF_PROXIES=1
```

and restart: `docker compose -f deploy/docker-compose.yml up -d`.

## 3. Your program

Sign up on the site, then load the Aesthetic 165 program for your account:

```bash
docker compose -f deploy/docker-compose.yml exec web \
    python3 manage.py seed_aesthetic165 --user <your-username> --current-weight 179
```

Other people who sign up start with an empty account: they set a goal under **Coach → Goal**
and build a routine under **Training**, or you run the seed command for them.

Food search needs wger's ingredient database (a large download, run once):

```bash
docker compose -f deploy/docker-compose.yml exec web wger load-online-fixtures
```

## 4. Updates

```bash
git pull
docker compose -f deploy/docker-compose.yml up -d --build
```

Migrations run automatically on start. Pushing to `main` on GitHub also builds the image and
publishes it as `ghcr.io/<you>/azone` (`.github/workflows/azone-image.yml`). To use it instead of
building on the server, replace `build:` in `docker-compose.yml` with
`image: ghcr.io/<you>/azone:latest` and run `docker compose pull && docker compose up -d`.

To pull in new wger releases: `git fetch upstream && git merge upstream/master`, run the tests,
then update as above.

## 5. Backups

Everything lives in the `postgres-data` volume (all logs, goals, measurements) and the `media`
volume (progress photos). A daily database dump:

```bash
docker compose -f deploy/docker-compose.yml exec -T db \
    pg_dump -U wger wger | gzip > "azone-$(date +%F).sql.gz"
```

## 6. Optional: nightly coach refresh

The dashboard refreshes its recommendations whenever it's opened. To also refresh them for everyone
overnight, add a cron job on the host:

```
30 4 * * * cd /path/to/AZone && docker compose -f deploy/docker-compose.yml exec -T web python3 manage.py coach_run_rules
```

## License

AZone is a modified version of wger, licensed AGPL-3.0. If other people use your instance, they
are entitled to its source code: keep the repository public (or otherwise offer them the source).
