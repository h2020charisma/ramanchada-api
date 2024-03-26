#!/usr/bin/env python
import os
import subprocess


def main():
    os.chdir('src')
    subprocess.run(['uvicorn', 'rcapi.main:app', '--reload', '--reload-dir', '.', '--reload-dir', '../extern'])
