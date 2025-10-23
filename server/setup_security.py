"""
Security Setup Script
Generates TLS certificates for C2 system

NOTE: This script runs AUTOMATICALLY when you start the server!
You only need to run this manually if you want to regenerate certificates.
"""

import os
import sys

print("=" * 60)
print("  C2 Security Setup")
print("=" * 60)
print()
print("NOTE: This runs automatically when you start the server!")
print("You only need to run this manually to regenerate certificates.")
print()

# Check for cryptography package
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from ipaddress import IPv4Address
    import datetime
except ImportError:
    print("[!] Error: cryptography package not found")
    print("[!] Install with: pip install cryptography")
    sys.exit(1)

print("[*] Generating TLS/SSL certificates...")

# Create certs directory
os.makedirs("certs", exist_ok=True)

# Generate private key
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Certificate subject and issuer (self-signed)
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "State"),
    x509.NameAttribute(NameOID.LOCALITY_NAME, "City"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "C2Server"),
    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
])

# Build certificate
cert = x509.CertificateBuilder().subject_name(
    subject
).issuer_name(
    issuer
).public_key(
    private_key.public_key()
).serial_number(
    x509.random_serial_number()
).not_valid_before(
    datetime.datetime.utcnow()
).not_valid_after(
    datetime.datetime.utcnow() + datetime.timedelta(days=365)
).add_extension(
    x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(IPv4Address("127.0.0.1")),
    ]),
    critical=False,
).sign(private_key, hashes.SHA256())

# Write private key
with open("certs/server.key", "wb") as f:
    f.write(private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ))

# Write certificate
with open("certs/server.crt", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print("    [+] Certificate: certs/server.crt")
print("    [+] Private key: certs/server.key")
print("    [+] Valid for: 365 days")
print()

print("=" * 60)
print("  Setup Complete!")
print("=" * 60)
print()
print("✅ Certificates generated successfully!")
print()
print("Next steps:")
print("  1. Start the server: python c2_server.py")
print("  2. Start the client: python c2_client.py")
print("  3. Follow the on-screen instructions!")
print()
print("Security features:")
print("  [+] TLS/SSL encryption (automatic)")
print("  [+] Per-client token authentication")
print("  [+] Approval workflow for new clients")
print("  [+] Token revocation and renewal")
print()
