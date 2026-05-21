#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  3 10:58:32 2024

@author: martin
"""

from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
import base64

# Public key in PEM format
public_key_pem = """-----BEGIN CERTIFICATE-----
MIIDFjCCAf6gAwIBAgIQGXyhKGxCTZlP7cIQCHGZNDANBgkqhkiG9w0BAQsFADBH
MUUwQwYDVQQDEzxBREZTIFNpZ25pbmcgLSBlY2xpcHNlLWFkZnMuYXVzdHJhbGlh
ZWFzdC5jbG91ZGFwcC5henVyZS5jb20wHhcNMjQwNDA5MjAxNDQ2WhcNMjUwNDA5
MjAxNDQ2WjBHMUUwQwYDVQQDEzxBREZTIFNpZ25pbmcgLSBlY2xpcHNlLWFkZnMu
YXVzdHJhbGlhZWFzdC5jbG91ZGFwcC5henVyZS5jb20wggEiMA0GCSqGSIb3DQEB
AQUAA4IBDwAwggEKAoIBAQC6mqDXpyFsBZW2X9Nfb8UB/ObViBjfd37U6rHkAHGS
n3JjZQ6Ds256h8+nbCIeTfeUZFMYvByr1PTxkWej0tnigphsCvKmxlYkR3bVPuYQ
HB+i7+d8tEA4wn2Ai6PBneN7/JXR5G1dBiQOnNFoOclUpJYlxel4Ag8BB43b9lYe
1tz9TTnKjtOLKUCkqRFSMF2LhivZ0CvfI5E+tLXFtVFg9HNDaa+J8udl+PNuGulc
FpzvINliG+BItGeCLesYpB13haVOn9ydg6xkd0QhBRokO7Ie4Gyklp4LIRt5uUwu
JwvO0hNe87/Tg6EHs8w4LUSP0cVi1DenksEiIKcC+gEBAgMBAAEwDQYJKoZIhvcN
AQELBQADggEBAEkrSfhUgw5FPKpx8+CcaExDLv2gLBlPriJ2dEDibeuF1OtrGq82
egQPZR3amG+w/e5rtRVJUGWL57vMQuIcNU8p/efOxo+vdNz2L9JLeR/cSyaH3cKj
labtAZ9+/YVyLWx5K9sFxAcxiz/gHPkyuz2kBvWhh+G7O4NqIdLZtFMc8aZXqukP
NoNfTyNti30uzsx47oZB2qJB5h3S/GNVidSQZ4MtA6rAcd4Fzd1ewpjJMA+QUJCP
gKoc9DIfQYtw6M3GbfNuOBZGD6DaTp8FZRVrY4c0LXFtC6UKifxpGG8Fp0XMCNCd
21gXQX7i71CL22/KCZ97YBJ0OlZA5oy0LN8=
-----END CERTIFICATE-----"""

# Load public key
public_key = RSA.import_key(public_key_pem)

# Data to verify
#data = b"<YourDataHere>"

# Base64 decode the signature
signature = base64.b64decode("XNAQEeNG2PkDuHqFkBTOT6gdMLGVeDgoBeGjwq0GXmEK8HMN+CV5XADEg3SG7PaZO/5Fd4WDlfFdy0rDgfSCrSe4IR/org2qh+axWNCmG6+aLpUxm/ZaZG5SkDNmqjoE5b361MOWjv/XwCofoyIp2ryiJLIHCiWILuv+Gwr+mbTvqucvdYuNkYnjQcMYj0l+2KfPK5aZxSkc+h2sJhUNjbi0o7K9QlfINq7bpChdI2JIQIMyDGYZfeALHuDivlCQNr/wa9BQJcCYBYftjfJ5FpzWwna9t04SNnn4yva2KKp//b1WoHGoKgpPo1QDCvmr0YlEJa1k7uhaoaG/xdduIQ==")

# Hash the data
h = base64.b64decode("sgPTyMsobOGnRtOHIaLLeCk6/H+FvcA6MqJg/K7DF2I=")

# Verify the signature
try:
    pkcs1_15.new(public_key).verify(h, signature)
    print("Signature is valid.")
except (ValueError, TypeError):
    print("Signature is invalid.")