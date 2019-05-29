import asyncio
import aiohttp
import click
from portcullis.server import PortcullisServer


async def main(config_file):
    server = PortcullisServer(config_file)
    await server.prepare_and_start()
    while True:
        await asyncio.sleep(3600)


@click.group()
@click.pass_context
def cli(ctx):
    pass

@cli.command(help="Starts Portcullis")
@click.argument("config_file")
def run(config_file):
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(main(config_file))
    except KeyboardInterrupt:
        pass

    loop.close()


if __name__ == "__main__":
    cli()
