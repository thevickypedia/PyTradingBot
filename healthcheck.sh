#!/bin/sh

curl -sf -H "X-Health-Check: true" "http://localhost:$PORT/health"
