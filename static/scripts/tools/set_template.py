#!/usr/bin/python3

import io
import os
import re
import sys

from gluon import current

def error(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(-1)

def templates(args):
    names = []
    for arg in args:
        names.extend(s for s in re.split(r"[\s;,\"\']", arg) if s)
    if not names:
        error("no template specified")
    return names

def setting(names):
    quote = lambda s: '"' + s + '"'
    if len(names) == 1:
        s = quote(names[0])
    else:
        s = "[" + ", ".join(quote(n) for n in names) + "]"
    return f"settings.base.template = {s}\n"

def validate(names):
    seen = set()
    for name in names:
        if name in seen:
            error(f"template repeated {name}")
        seen.add(name)
        package = f"templates.{name}"
        try:
            getattr(__import__(package, fromlist=["config"]), "config")
        except ImportError:
            raise RuntimeError(f"Template '{name}' not found")
        except AttributeError:
            raise RuntimeError(f"Invalid template '{name}'")
    return names

def configure(s):
    config = os.path.join(current.request.folder, "models", "000_config.py")
    buf = io.StringIO()
    with open(config, "r", encoding="utf-8") as config_file:
        buf.write(config_file.read())
    buf.seek(0)
    with open(config, "w", encoding="utf-8") as config_file:
        for line in buf:
            if re.match(r"settings\.base\.template.*", line):
                output = s
            else:
                output = line
            config_file.write(output)

if __name__ == "__main__":

    args = sys.argv[1:]
    if not args:
        error("missing arguments")

    names = validate(templates(args))
    print(names)
    configure(setting(names))
