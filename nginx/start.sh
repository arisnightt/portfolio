#!/bin/sh
set -eu

if [ -s /etc/letsencrypt/live/arisnight.dpdns.org/fullchain.pem ] \
    && [ -s /etc/letsencrypt/live/arisnight.dpdns.org/privkey.pem ]; then
    cp /opt/nginx-templates/https.conf /etc/nginx/conf.d/default.conf
else
    cp /opt/nginx-templates/http.conf /etc/nginx/conf.d/default.conf
fi

exec nginx -g 'daemon off;'