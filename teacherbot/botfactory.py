# -*- coding: utf-8 -*-

from twisted.internet import protocol, reactor, error
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
        self.config = config
        self.stop = False
        self.dbclient = MongoClient(config["database"])
        self.db = self.dbclient.chat_bot
        self.db.chat_bot.users.ensure_index("username", unique=True)
        self.db.chat_bot.users.ensure_index(
            [("hostmask", pymongo.ASCENDING),
            ("password", pymongo.ASCENDING),
            ("role", pymongo.ASCENDING),
            ("nick", pymongo.ASCENDING)])

    def clientConnectionLost(self, connector, reason):
        """If we get disconnected, reconnect to server."""

        r = reason.trap(error.ConnectionDone)

        if r == error.ConnectionDone:
            if self.stop:
                self.dbclient.disconnect()
                reactor.stop()
            else:
                protocol.ReconnectingClientFactory.clientConnectionLost(self,
                connector, reason)
        else:
            protocol.ReconnectingClientFactory.clientConnectionLost(self,
                connector, reason)
            log.err(reason)

    def clientConnectionFailed(self, connector, reason):
        """Is run if the connection fails."""
        self.dbclient.disconnect()
        log.err(reason)
        reactor.stop()