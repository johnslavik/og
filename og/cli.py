import sys

import click


@click.group(sys.argv[0])
def cli() -> None:
    pass


if __name__ == "__main__":
    cli()
