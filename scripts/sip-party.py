#!/usr/bin/env python
"""sip-party.py

An interactive script for making phone calls, to demonstrate the sipparty APIs.

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from __future__ import print_function
import argparse
from collections import Callable
import logging
from sipparty.parties import SingleRTPSessionSimplenParty
from sys import (exit, stdin, stdout)
from time import sleep

log = logging.getLogger(__name__)


class SIPPartyException(Exception):
    pass


class NoSuchCommandException(SIPPartyException):
    pass


class BadArgumentException(SIPPartyException):
    pass


class SIPPartyArgs(argparse.ArgumentParser):
    "Argument parser for the script."

    def __init__(self):
        super(SIPPartyArgs, self).__init__()
        self.add_argument(
            '--debug', '-D', type=int, nargs='?', help='Turn on debugging',
            default=logging.WARNING)

        self.args = self.parse_args()

        if self.args.debug is None:
            self.args.debug = logging.DEBUG


class SIPPartyRunLoop(object):

    def __init__(self):
        super(SIPPartyRunLoop, self).__init__()
        self.extra_help = True
        self.exit = False

        self._sprl_input = stdin
        self._sprl_output = stdout
        self._sprl_command_dict = {}
        self._fix_commands()
        self._sprl_party = SingleRTPSessionSimplenParty()

    def _fix_commands(self):
        command_method_prepend = 'command_'
        for attr in dir(self):
            if attr.startswith(command_method_prepend):
                log.debug('Adding command method %r', attr)
                command_method_name = attr.replace(command_method_prepend, '')
                method = getattr(self, attr)
                method.__dict__['attr_name'] = command_method_name
                assert isinstance(method, Callable)
                self._add_command_stub(
                    command_method_name,
                    method,
                    self._sprl_command_dict)
                log.debug(
                    'Dict after command stub add: %r', self._sprl_command_dict)

    def _add_command_stub(self, cmd_stub, cmd_method, cmd_dict):
        assert isinstance(cmd_stub, str)
        log.debug('Add command stub %r', cmd_stub)
        if len(cmd_stub) == 0:
            cmd_dict[cmd_stub] = cmd_method
            return

        first_letter = cmd_stub[0]

        if first_letter in cmd_dict:
            log.debug('Existing entry with first letter %r', first_letter)
            existing_obj = cmd_dict[first_letter]
            if isinstance(existing_obj, str):
                # Have an existing command starting with this letter.
                log.debug('Existing string entry; replace with dict.')
                existing_method = cmd_dict[existing_obj]
                del cmd_dict[existing_obj]
                sub_dict = {}
                cmd_dict[first_letter] = sub_dict
                self._add_command_stub(
                    existing_obj[1:], existing_method, sub_dict)
            else:
                sub_dict = existing_obj

            self._add_command_stub(cmd_stub[1:], cmd_method, sub_dict)

        else:
            cmd_dict[first_letter] = cmd_stub
            cmd_dict[cmd_stub] = cmd_method

    #
    # =================== Standard commands. ==================================
    #
    def command_exit(self, arg):
        self.exit = True

    def command_listen(self, arg):
        self._sprl_party.listen(address_name=arg)

    def command_set(self, arg):
        log.debug('set %r', arg)

    def command_sleep(self, arg):
        try:
            time_to_sleep = float(arg)
        except ValueError:
            raise BadArgumentException(
                'Argument to sleep command %r is not a number.' % arg)

        sleep(time_to_sleep)

    #
    # =================== Interactions with the user ==========================
    #
    def printChars(self, text, *args):
        print(text % args, end='', file=self._sprl_output)
        self._sprl_output.flush()

    def displayToUser(self, text='', *args):
        self.printChars(('%s\n' % text) % args)

    def displayExtraHelp(self, text='', *args):
        if not self.extra_help:
            return
        self.displayToUser('-> %s' % text, *args)

    def showWelcomeScreen(self):
        self.displayToUser('Welcome to SIP Party!')
        self.displayToUser()

    def showLoopText(self):
        if not hasattr(self._sprl_party, 'listenAddress'):
            self.displayToUser('Inactive party and not listening.')
            self.displayExtraHelp(
                'Use command \'listen\' to get a local address and start '
                'listening.')
        else:
            self.displayToUser(
                'Party listening on: %s', self._sprl_party.listenAddress)

    def getUserInput(self):
        self.printChars('> ')
        return self._sprl_input.readline()

    def getCommandFromString(self, string, sub_dict):
        log.debug('Get substring command %r', string)
        if string in sub_dict:
            poss_cmd = sub_dict[string]
            if isinstance(poss_cmd, Callable):
                log.debug('Returning callable for string %r', string)
                return poss_cmd

            if isinstance(poss_cmd, str):
                log.debug('Returning substr %r', poss_cmd)
                return sub_dict[sub_dict[poss_cmd]]

            return self.getCommandFromString(self, string[1:], poss_cmd)

        if len(string) == 0:
            raise NoSuchCommandException()

        first_letter = string[0]
        if first_letter not in sub_dict:
            raise NoSuchCommandException()

        cmd_poss = sub_dict[first_letter]
        if isinstance(cmd_poss, str):
            log.debug('Found command at substring %r', cmd_poss)
            return sub_dict[cmd_poss]

        log.debug('Recurse')
        return self.getCommandFromString(string[1:], cmd_poss)

    def nextCommand(self):

        for attempts in range(5):
            inp = self.getUserInput().strip()
            (command, space, args) = inp.partition(' ')
            command = command.strip()
            try:
                cmd_method = self.getCommandFromString(
                    command, self._sprl_command_dict)
                self.displayToUser(cmd_method.attr_name)
            except NoSuchCommandException:
                self.displayToUser('No such command %r', inp)
                continue

            return cmd_method, args.strip()

    def run(self):

        self.showWelcomeScreen()

        while not self.exit:

            self.showLoopText()
            try:
                command, args = self.nextCommand()
            except KeyboardInterrupt:
                self.exit = True
                continue

            try:
                log.debug('Running command %r', command)
                command(args)
            except BadArgumentException as exc:
                self.displayToUser(
                    'Invalid argument to command %r: %s', command.__name__,
                    exc)
            except Exception as exc:
                log.exception(
                    'Exception hit running command %r', command.attr_name)


#
# =================== Main script. =======================================
#
def main():
    args = SIPPartyArgs().args

    if args.debug < logging.INFO:
        log.setLevel(args.debug)
        for suppress in (
                'sipparty.util', 'sipparty.deepclass',
                'sipparty.fsm.retrythread'):
            logging.getLogger(suppress).setLevel(logging.INFO)

    rl = SIPPartyRunLoop()

    rl.run()


if __name__ == '__main__':
    log = logging.getLogger()
    logging.basicConfig()
    log.setLevel(logging.INFO)
    exit(main())
