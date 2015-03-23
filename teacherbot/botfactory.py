# -*- coding: utf-8 -*-

from twisted.internet import protocol, reactor
from twisted.python import log
from pymongo import MongoClient
import pymongo
from .bot import Bot


class BotFactory(protocol.ReconnectingClientFactory):
    """A factory for Bots.

    A new protocol instance will be created each time we connect to the server.
    """

    protocol = Bot

    def __init__(self, config):
        """Init"""

        self.nickname = config['network'].get('nickname',
            config["identity"]["nickname"]).encode('utf8')
        self.password = config['network']['password'].encode('utf8')
        self.username = config['network'].get('username',
            config["identity"]["nickname"]).encode('utf8')
        self.realname = config['network'].get('realname',
            config["identity"]["nickname"]).encode('utf8')
        self.linerate = config['general']['linerate']
        self.dbclient = None
        self.db = None
        self.config = config

    def startFactory(self):
        """Called when starting factory"""
        self.dbclient = MongoClient(self.config["database"])
        self.db = self.dbclient.chat_bot
        self.db.chat_bot.users.ensure_index("username", unique=True)
        self.db.chat_bot.users.ensure_index(
            [("hostmask", pymongo.ASCENDING),
            ("password", pymongo.ASCENDING),
            ("role", pymongo.ASCENDING),
            ("nick", pymongo.ASCENDING)])
        self.db.chat_bot.kicklist.ensure_index("hostmask", unique=True)
        self.db.chat_bot.chan_settings.ensure_index("channel", unique=True)

        protocol.ReconnectingClientFactory.startFactory(self)

    def stopFactory(self):
        """Called when stopping factory"""
        self.dbclient.disconnect()
        protocol.ReconnectingClientFactory.stopFactory(self)

        if reactor.running:
            reactor.stop()

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""

        protocol.ReconnectingClientFactory.clientConnectionLost(self,
            connector, reason)

    def clientConnectionFailed(self, connector, reason):
        """Is run if the connection fails."""
        log.err(reason)

        protocol.ReconnectingClientFactory.clientConnectionLost(self,
            connector, reason)