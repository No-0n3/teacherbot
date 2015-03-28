# -*- coding: utf-8 -*-

from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker
from twisted.application import service
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.python import log

from teacherbot import BotFactory
import json


class Options(usage.Options):
    """A class to parse commandline options"""
    optParameters = [["config", "c", "config.json", "The configfile to use."], ]


class BotService(service.Service):
    """Custom service for IRC-Bot"""

    _bot = None

    def __init__(self, config):
        """Init"""
        self.config = config

    def startService(self):
        """Start service"""
        from twisted.internet import reactor

        def connected(bot):
            """Called on success"""
            self._bot = bot

        def failure(err):
            """Called at error"""
            log.err(err, _why='Could not connect to specified server.')
            reactor.stop()

        client = TCP4ClientEndpoint(reactor, self.config['network']["host"],
            self.config['network']["port"])
        factory = BotFactory(self.config)

        return client.connect(factory).addCallbacks(connected, failure)

    def stopService(self):
        """Stop service"""
        if self._bot and self._bot.transport.connected:
            self._bot.transport.loseConnection()
            self._bot.factory.dbclient.disconnect()


class BotServiceMaker(object):
    """Class to create a service."""

    implements(IServiceMaker, IPlugin)
    tapname = "teacherbot"
    description = "Teacherbot - An IRC-Bot to that" \
        " helps you keep your channels clean."
    options = Options

    def makeService(self, options):
        """
        Construct a TCPServer from a factory defined in myproject.
        """

        with open(options['config'], "rb") as f:
            config = json.load(f)

        return BotService(config)

botservice = BotServiceMaker()
