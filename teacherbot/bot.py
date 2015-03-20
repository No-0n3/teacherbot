# -*- coding: utf-8 -*-
import hashlib
from functools import wraps
from twisted.words.protocols import irc
from twisted.internet import threads
from twisted.python import log
from pymongo.errors import DuplicateKeyError


# Decorator to check so the user has permission to use the function.
def has_permission(role):
    """Decorator that checks so user has correct permissions."""

    def permission_decorator(func):
        """Decorator function"""

        @wraps(func)
        def wrapped_func(self, user, src_chan, *args, **kwargs):
            """Wrapped function"""
            coll = self.factory.db.users

            user_doc = coll.find_one({"hostmask": user.split('!', 1)[1]})

            if user_doc is not None and user_doc['role'][role]:
                func(self, user, src_chan, *args, **kwargs)
            else:
                self.notice(user.split('!', 1)[0], "Perrmission denied!")

        return wrapped_func
    return permission_decorator


class Bot(irc.IRCClient):
    """ChatBot class"""

    nickname = ""
    password = ""
    username = ""
    realname = ""

    def connectionMade(self):
        """Is run when the connection is successful."""
        self.nickname = self.factory.nickname
        self.password = self.factory.password
        self.username = self.factory.username
        self.realname = self.factory.realname
        self.linerate = self.factory.linerate

        irc.IRCClient.connectionMade(self)

    def connectionLost(self, reason):
        """Is run if the connection is lost."""
        irc.IRCClient.connectionLost(self, reason)

    # callbacks for events
    def signedOn(self):
        """Called when bot has succesfully signed on to server."""
        pass

    def kickedFrom(self, channel, kicker, message):
        """Called when I am kicked from a channel."""
        self.join(channel)
        log.msg("I was kicked from {} by {} because: {}".format(
            channel, kicker, message))

    def joined(self, channel):
        """This will get called when the bot joins the channel."""
        log.msg("I joined {}".format(channel))

    def noticed(self, user, channel, msg):
        """Called when a notice is recieved."""
        log.msg("From %s/%s: %s" % (user, channel, msg))

    def privmsg(self, user, channel, msg):
        """This will get called when the bot receives a message."""

        if msg.startswith("@"):
            cmd = msg.split()[0].strip("@")
            args = msg.split()[1:] or [None, ]

            func = getattr(self, 'cmd_' + cmd, None)

            if func is not None:
                threads.deferToThread(func, user,
                    channel, *args)
            else:
                self.notice(user.split('!', 1)[0], "Unknown command!")

    def userQuit(self, user, quitMessage):
        """Called when a user leaves the network"""
        coll = self.factory.db.users
        user_doc = coll.find_one({"nick": user})

        if user_doc is not None:
            user_doc['hostmask'] = ""
            user_doc['nick'] = ""
            coll.save(user_doc)
            log.msg("User {} was automaticlly logged off.".format(user))

    def userRenamed(self, oldname, newname):
        """Called when a user changes nick"""
        coll = self.factory.db.users
        user_doc = coll.find_one({"nick": oldname})

        if user_doc is not None:
            user_doc['nick'] = newname
            coll.save(user_doc)
            log.msg("User {} changed nick to {}".format(oldname, newname))

    # User-defined commands
    @has_permission("op")
    def cmd_join(self, user, src_chan, channel, password=None):
        """Join a channel. @join <channel> [<password>]"""
        if channel:
            self.join(channel, password)

    @has_permission("op")
    def cmd_part(self, user, src_chan, channel, password=None):
        """Leave a channel. @part <channel>"""
        if channel:
            self.part(channel)

    @has_permission("user")
    def cmd_help(self, user, src_chan, cmd=None):
        """Lists help about commands. @help [<cmd>]"""
        user = user.split('!', 1)[0]

        if cmd is None:
            self.notice(user, "Commands:")

            for func in dir(self):
                if func.startswith("cmd_"):
                    self.notice(user, "@" + func[4:] + " - " +
                                getattr(self, func).__doc__)
        else:
            func = getattr(self, "cmd_" + cmd)
            self.notice(user, "@" + func.__name__[4:] + " - " + func.__doc__)

    @has_permission("admin")
    def cmd_quit(self, user, src_chan, *args):
        """Shutdown the bot."""
        self.quit(message="Shutting down.")
        self.factory.stop = True

    @has_permission("admin")
    def cmd_msg(self, user, src_chan, dest, message):
        """Tell the bot to send a message. @msg <user> <message>"""
        if dest and message:
            self.msg(dest, message)

    def cmd_auth(self, user, src_chan, username, password):
        """Authenticate with the bot. @auth <username> <password>"""
        m = hashlib.sha512()
        m.update(password)
        password = m.hexdigest()

        coll = self.factory.db.users
        user_doc = coll.find_one({"username": username, "password": password})

        if user_doc:
            self.notice(user.split('!', 1)[0], "I recognize you.")

            user_doc["hostmask"] = user.split('!', 1)[1]
            user_doc["nick"] = user.split('!', 1)[0]
            coll.save(user_doc)
        else:
            self.notice(user.split('!', 1)[0], "I don't know you.")

    def cmd_register(self, user, src_chan, username, password):
        """Register your nickname to the bot. @register <username> <password>"""
        m = hashlib.sha512()
        m.update(password)

        user_doc = {
            "username": username,
            "password": m.hexdigest(),
            "hostmask": user.split('!', 1)[1],
            "role": {"user": True, "admin": False, "op": False, "owner": False},
            "nick": user.split('!', 1)[0]
            }

        coll = self.factory.db.users

        try:
            coll.insert(user_doc)
        except DuplicateKeyError:
            self.notice(user.split('!', 1)[0],
                "Username already in use.")
        else:
            self.notice(user.split('!', 1)[0],
                "Your username is now registered.")

    @has_permission("user")
    def cmd_remove(self, user, src_chan, username, password):
        """Unregister your nickname from the bot. @remove """
        """<username> <password>"""
        m = hashlib.sha512()
        m.update(password)
        password = m.hexdigest()

        coll = self.factory.db.users
        user_doc = coll.find_one({"username": username, "password": password})

        if user_doc is not None:
            coll.remove(user_doc["_id"])
            self.notice(user.split('!', 1)[0],
                "Your nickname has been removed.")
        else:
            self.notice(user.split('!', 1)[0],
                "Your nickname could not be removed!")

    @has_permission("admin")
    def cmd_op(self, user, src_chan, username):
        """Escalate privileges to operator level for a user. @op <username>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['op'] = True
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User have now been opped!")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("admin")
    def cmd_deop(self, user, src_chan, username):
        """Remove operator privilege from a user. @deop <username>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['op'] = False
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User have now been deopped!")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")
