# pp-terminal - The Analytic Companion for Portfolio Performance

![build status](https://github.com/ma4nn/pp-terminal/actions/workflows/ci.yml/badge.svg) [![Join My Discord](https://dev-investor.de/wp-content/uploads/join-discord.svg)](https://dev-investor.de/chat)

A powerful command-line tool that uses the openness of [Portfolio Performance](https://www.portfolio-performance.info/) data 
and the convenient access of [ppxml2db](https://github.com/pfalcon/ppxml2db) to offer a whole new level of insights into your portfolio.  

For example, _pp-terminal_ includes a command to calculate the preliminary tax values ("Vorabpauschale") for Germany:

![Vorabpauschale command in pp-terminal](docs/sample_vorabpauschale.png)

_pp-terminal_ is a lightweight tool for all the nice-to-have features that won't make it into the official Portfolio Performance app.
This can be because of country-dependant tax rules, complex Java implementation, highly individual requirements, 
too many edge-cases, etc.

> [!IMPORTANT]
> I am not a tax consultant. All results of this application are just a non-binding indication and without guarantee.
> They may deviate from the actual values.

## Commands

Code completion for commands and options is available.  
You can choose between different output formats like JSON or CSV with the `--format` option.

In addition to the standard set, you can easily [create your own commands](#user-content-create-your-own-command-️) 
and share them with the community.

By default, `pp-terminal --help` provides the following commands:

### Inspect Portfolio

| Command           | Description                                                                            |
|-------------------|----------------------------------------------------------------------------------------|
| `view accounts`   | Get detailed information about the balances per each deposit and/or securities account |
| `view securities` | Get detailed information about the securities                                          |

The commands can be customized in the [configuration file](#configuration-file):
```toml
[commands.view.accounts]
columns = ["AccountId", "Name", "Balance"]

[commands.view.securities]
columns = ["SecurityId", "Name", "Shares"]
```

### Simulate Scenarios

| Command                   | Description                                                                                        |
|---------------------------|----------------------------------------------------------------------------------------------------|
| `simulate interest`       | Calculate how much interest you should have been earned per account and compare with actual values |
| `simulate share-sell`     | Calculate gains and taxes if a security would be sold (based on FIFO capital gains)                |
| `simulate vorabpauschale` | Run a simulation for the German preliminary tax ("Vorabpauschale") on the portfolio                |

### Validate Data

| Command               | Description                                                 |
|-----------------------|-------------------------------------------------------------|
| `validate`            | Run all validation checks on the portfolio data             |
| `validate accounts`   | Run configured accounts validations, e.g. balance limits    |
| `validate securities` | Run configured security validations, e.g. prices up-to-date |

The commands can be customized in the [configuration file](#configuration-file):
```toml
# Note: order of rules is relevant

[[commands.validate.accounts.rules]]
type = "balance-limit"
value = 25000
applies-to = ["c9c57e01-7ea0-4e70-bed9-4656941f7687"]

[[commands.validate.accounts.rules]]
type = "balance-limit"
value = 100000

[[commands.validate.accounts.rules]]
type = "date-passed-from-attribute"
value = "fgdeb0dd-8bd7-47b1-ac3f-30fedd6a47e9"

[[commands.validate.securities.rules]]
type = "price-staleness"
value = 90

[[commands.validate.securities.rules]]
type = "price-staleness"
severity = "warning"
value = 30
```

### Export

| Command             | Description                                                      |
|---------------------|------------------------------------------------------------------|
| `export anonymized` | Save an anonymized version of the Portfolio Performance XML file |

The command can be customized in the [configuration file](#configuration-file):
```toml
[commands.export.anonymized.attributes."a1b2c3d4-e5f6-7890-abcd-ef1234567890"]
provider = "iban"

[commands.export.anonymized.attributes."fgdeb0dd-8bd7-47b1-ac3f-30fedd6a47e9"]
provider = "pyfloat"
args = { min_value = 0.0, max_value = 1.0, right_digits = 2 }
```

## Requirements

- [pipx](https://pipx.pypa.io/latest/#install-pipx) to install the application (without having to worry about different Python runtimes)
- Portfolio Performance version >= 0.70.3
- Portfolio Performance file must be saved as "XML with id attributes"

## Installing

```
pipx install pp-terminal
```

Once installed, update to the latest with:

```
pipx upgrade pp-terminal
```

## Usage 💡

### Portfolio Performance XML File
> [!TIP]
> The application **does not modify** the original Portfolio Performance file and works completely offline.

All commands require the Portfolio Performance XML file as input.    
You can either provide that file as first option to the command
```
pp-terminal --file=depot.xml view accounts
```
or use a configuration file (see below).

To view all available arguments you can always use the `--help` option.

### Configuration File
To persist the CLI options you can pass a configuration file with `pp-terminal --config=config.toml --help`.

The TOML format supports comments and is more readable than JSON for complex configurations.

```toml
file = "portfolio_performance.xml"
precision = 4

[tax]
rate = 26.375
file = "vorabpauschale.csv"
exemption-rate = 30
exemption-rate-attribute = "b3c38686-2d22-4b5d-8e38-e61dcf6fdde3"
```

### Customize Number Formats
If you want another formatting for numbers, assure that the terminal has the correct language settings, e.g. for Germany 
set environment variable `LANG=de_DE.UTF-8`.

### Disable Colored Output
To disable all colors in the console output for a better readability, you can set the `NO_COLOR=1` [environment variable](https://no-color.org/).

## Contributing

### Propose Changes

To contribute improvements to _pp-terminal_ just follow these steps:

1. Fork and clone this repository
2. Run `make`
3. Verify build with `poetry run pp-terminal --version`
4. Create a new branch based on `master`: `git checkout master && git pull && git checkout -b your-patch`
5. Implement your changes in this new branch
6. Run `make` to verify everything is fine
7. Submit a [Pull Request](https://docs.github.com/de/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests)

### Create Your Own Command ⚒️

Developers can easily extend the default _pp-terminal_ functionality by implementing their own commands. Therefore, the Python
[entry point](https://packaging.python.org/en/latest/specifications/entry-points/) `pp_terminal.commands` is provided.
To hook into a sub-command, e.g. `view`, you have to prefix the entry point name with `view.`.

The most basic _pp-terminal_ command looks like this:

```python
from pp_terminal.output import Console
import typer

app = typer.Typer()
console = Console()


@app.command
def hello_world() -> None:
    console.print("Hello World")
```
This will result in the command `pp-terminal hello-world` being available.

For more sophisticated samples take a look at the packaged commands in the `pp_terminal/commands` directory,
e.g. a good starting point is [view_accounts.py](https://github.com/ma4nn/pp-terminal/blob/master/pp_terminal/commands/view_accounts.py).

The app uses [Typer](https://typer.tiangolo.com/) for composing the commands and [Rich](https://github.com/Textualize/rich)
for nice console outputs. The Portfolio Performance XML file is read with [ppxml2db](https://github.com/pfalcon/ppxml2db) 
and efficiently held in [pandas dataframes](https://pandas.pydata.org/).

If your command makes sense for a broader audience, I'm happy to accept a [pull request](#propose-changes).

## Known Limitations 🚧

- The script is still in beta version, so there might be Portfolio Performance files that are not compatible with and also public APIs can change

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0). See the [LICENSE](./LICENSE) file for more details.
