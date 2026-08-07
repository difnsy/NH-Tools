import asyncio
# Mengambil fungsi dari file nh.py milikmu
from nh import load_data, run_claim_process

async def main():
    data = load_data()
    if data:
        await run_claim_process(data)

if __name__ == '__main__':
    asyncio.run(main())