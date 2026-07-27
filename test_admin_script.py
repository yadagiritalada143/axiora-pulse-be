import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "http://localhost:8000/api/v1/auth/admin/login",
            json={
                "username": "admin@axiorapulse.com",
                "password": "Test@12345"
            }
        )
        print("STATUS:", res.status_code)
        print("BODY:", res.json())

if __name__ == "__main__":
    asyncio.run(main())
