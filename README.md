# pp-terminal - The Analytic Companion for Portfolio Performance

![build status](https://github.com/ma4nn/pp-terminal/actions/workflows/ci.yml/badge.svg)

A powerful command-line tool that uses the openness of [Portfolio Performance](https://www.portfolio-performance.info/) data 
and the convenient access of [ppxml2db](https://github.com/pfalcon/ppxml2db) to offer a whole new level of insights into your portfolio.  

For example, _pp-terminal_ includes a command to calculate the preliminary tax values ("Vorabpauschale") for Germany:

![Vorabpauschale command in pp-terminal](sample_vorabpauschale.png)

_pp-terminal_ is a lightweight tool for all the nice-to-have features that won't make it into the official Portfolio Performance app.
This can be because of country-dependant tax rules, complex Java implementation, highly individual requirements, 
too many edge-cases, etc.

By default, `pp-terminal` provides the following commands:

| Command                   | Description                                                                                        |
|---------------------------|----------------------------------------------------------------------------------------------------|
| `list accounts`           | Get detailed information about the balances per each deposit and/or securities account             |
| `simulate interest`       | Calculate how much interest you should have been earned per account and compare with actual        |
| `simulate vorabpauschale` | Run a simulation for the German preliminary tax ("Vorabpauschale") on the portfolio                |
| `validate`                | Run a number of different validation checks on the portfolio data, e.g. security prices up-to-date |

Code completion for commands and options is available.  
The application **does not modify** the original Portfolio Performance file.  
You can choose between different output formats like JSON or CSV with the `--format` option.

In addition to the standard set, you can easily [create your own commands](#user-content-create-your-own-command-️) 
and share them with the community.

> [!IMPORTANT]
> I am not a tax consultant. All results of this application are non-binding and without guarantee.
> They may deviate from the actual values.

## Requirements

- [pipx](https://pipx.pypa.io/latest/#install-pipx) to install the application (without having to worry about different Python runtimes)
- Portfolio Performance version >= 0.70.3
- Portfolio Performance file must be saved as "XML with id attributes"

## Installing

```
pipx install pp-terminal
```

## Usage 💡

The commands mentioned above all require the Portfolio Performance XML file as input.  
You can either provide that file as first option to the command
```
pp-terminal --file=depot.xml list accounts
```
or by setting an environment variable you can omit the option
```
export PP_TERMINAL_INPUT_FILE=depot.xml
pp-terminal list accounts
```

To view all available arguments you can always use the `--help` option.

### Customize Number Formats
If you want another formatting for numbers, assure that the terminal has the correct language settings, e.g. for Germany:
```
export LANG=de_DE.UTF-8
```

### Disable Colored Output
To disable all colors in the console output for a better readability, you can set the `NO_COLOR` [environment variable](https://no-color.org/)
to any value like this
```
export NO_COLOR=1
```

## Create Your Own Command ⚒️

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
and efficiently held in [panda dataframes](https://pandas.pydata.org/).

If your command makes sense for a broader audience, I'm happy to accept a pull request.

## Known Limitations 🚧

- The script is still in beta version, so there might be Portfolio Performance files that are not compatible with and also public APIs can change

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0). See the [LICENSE](./LICENSE) file for more details.
