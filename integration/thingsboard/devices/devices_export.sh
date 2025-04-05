#! /bin/bash

curl -X GET "http://localhost:8080/api/tenant/devices?pageSize=1000&page=0" \
  -H "Content-Type: application/json" \
  -H "X-Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -o devices_export.json