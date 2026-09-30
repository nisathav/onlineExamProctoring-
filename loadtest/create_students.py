"""Create load-test students (load001..loadNNN) with consent recorded, via the API.

Usage: python loadtest/create_students.py --count 100 [--host http://localhost:8000]
"""
import argparse

import httpx

from locustfile import PASSWORD


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--host", default="http://localhost:8000")
    args = parser.parse_args()

    with httpx.Client(base_url=args.host, timeout=30) as client:
        for i in range(1, args.count + 1):
            username = f"load{i:03d}"
            client.post("/auth/register", json={
                "username": username, "email": f"{username}@load.test", "password": PASSWORD})
            token = client.post("/auth/token", data={"username": username, "password": PASSWORD}).json()["access_token"]
            client.post("/auth/consent", headers={"Authorization": f"Bearer {token}"}).raise_for_status()
    print(f"{args.count} load-test students ready")


if __name__ == "__main__":
    main()
