#! /bin/bash

curl -X POST "http://localhost:8080/api/auth/login" -H "Content-Type: application/json" -d '{"username":"tenant@thingsboard.org", "password":"tenant"}'