# -*- coding: utf-8 -*-
import hashlib
from functools import wraps
from twisted.words.protocols import irc
from twisted.internet import threads
from twisted.python import log
from pymongo.errors import DuplicateKeyError
from badwords import Badwords


# Decorator to check so the user has permission to use the function.
def has_permission(role, channel=None):
    """Decorator that checks so user has correct permissions."""

    def permission_decorator(func):
        """Decorator function"""

        @wraps(func)
        def wrapped_func(self, user, src_chan, *args, **kwargs):
            """Wrapped function"""
            coll = self.factory.db.users

            user_doc = coll.find_one({"hostmask": user.split('!', 1)[1]})

            if user_doc is not None and user_doc['role'][role]:
                if channel is not None:
                    if len(args) > channel:
                        if args[channel] in user_doc['channels'] \
                            or user_doc["all"]:
                            func(self, user, src_chan, *args, **kwargs)
                        else:
                            self.notice(user.split('!', 1)[0],
                                "Permission denied!")
                    else:
                        self.notice(user.split('!', 1)[0],
                                "No channel given.")
                else:
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
    engine = None

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
        self.engine = Badwords(self.factory.db)

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

    # A callback that gets a result after checking a word and kicks a user by
    # sending a command to ChanServ with a reason.
    def badword(self, result, user, channel):
        """Is called when a search of the text engine is done."""
        if result:
            kicklist = self.factory.db.kicklist
            record = kicklist.find_one({"hostmask": user.split('!', 1)[1]})
            cs = self.factory.db.chan_settings.find_one({"channel": channel})

            if record is None:
                record = {
                    "hostmask": user.split('!', 1)[1],
                    "warns": 0,
                    "kicks": 0,
                    }

                kicklist.save(record)

            record = kicklist.find_one({"hostmask": user.split('!', 1)[1]})
            log.msg("%r" % record)

            if cs['kicker'] and record["warns"] >= cs['ttk']:
                self.msg(cs['chanserv'].encode('utf8'),
                    cs['cmd_kick'].encode('utf8').format(
                        channel=channel,
                        user=user.split('!', 1)[0],
                        reason=cs['kick_reason'].encode('utf8')
                        ))
                record['warns'] = 0
                record['kicks'] += 1
            elif cs['ban'] and record["kicks"] >= cs['ttb']:
                self.msg(cs['chanserv'].encode('utf8'),
                    cs['cmd_atb'].encode('utf8').format(
                        channel=channel,
                        user=user.split('!', 1)[0],
                        bantime=cs['bantime'],
                        reason=cs['ban_reason'].encode('utf8').format(
                            bantime=cs['bantime'])
                        ))
                record['kicks'] = 0
                record['warns'] = 0
            else:
                if cs['private']:
                    self.notice(user.split('!', 1)[0], "Watch your language!")
                else:
                    self.msg(channel, "Watch your language %s!"
                        % user.split('!', 1)[0])

                record['warns'] += 1

            kicklist.save(record)

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
        else:
            if channel.startswith("#"):
                # Run defer in thread so it doesn't block if many results in db.
                d = threads.deferToThread(self.engine.check, channel, msg)
                d.addCallback(self.badword, user, channel)

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
    @has_permission("op", 0)
    def cmd_join(self, user, src_chan, channel, password=None):
        """Join a channel. @join <channel> [<password>]"""
        if channel:
            coll = self.factory.db.chan_settings
            cs = coll.find_one({"channel": channel})

            if cs is None:
                cs = {
                    "channel": channel,
                    "ttb": 3,
                    "ttk": 3,
                    "kicker": False,
                    "ban": False,
                    "private": True,
                    "bantime": 60,
                    "cmd_atb": "",
                    "cmd_kick": "",
                    "chanserv": "ChanServ",
                    "kick_reason": "Watch you language!",
                    "ban_reason": "Watch your language!"
                    }

                coll.save(cs)

            self.join(channel, password)

    @has_permission("op", 0)
    def cmd_part(self, user, src_chan, channel, password=None):
        """Leave a channel. @part <channel>"""
        if channel:
            self.part(channel)

    @has_permission("owner")
    def cmd_quit(self, user, src_chan, *args):
        """Shutdown the bot."""
        self.quit(message="Shutting down.")
        self.factory.stop = True

    @has_permission("admin")
    def cmd_msg(self, user, src_chan, dest, *message):
        """Tell the bot to send a message. @msg <user> <message>"""
        if dest and message:
            self.msg(dest, ' '.join(message))

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
            "nick": user.split('!', 1)[0],
            "channels": {},
            "all": False
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

    @has_permission("admin", 1)
    def cmd_op(self, user, src_chan, username, channel):
        """Escalate privileges to operator level for a user. @op <username>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['user'] = True
            user_doc['role']['op'] = True
            user_doc['role']['admin'] = False
            user_doc['role']['owner'] = False
            user_doc['channels'][channel] = None
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User have now been opped!")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("admin", 1)
    def cmd_deop(self, user, src_chan, username, channel):
        """Remove operator privilege from a user. @deop <username> <channel>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['user'] = True
            user_doc['role']['op'] = False
            user_doc['role']['admin'] = False
            user_doc['role']['owner'] = False
            del user_doc['channels'][channel]
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User have now been deopped!")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("admin", 1)
    def cmd_admin(self, user, src_chan, username, channel):
        """Escalate privileges to admin level for a user. @admin <username>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['user'] = True
            user_doc['role']['op'] = True
            user_doc['role']['admin'] = True
            user_doc['role']['owner'] = False
            user_doc['channels'][channel] = None
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User have now been admined!")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("admin", 1)
    def cmd_deadmin(self, user, src_chan, username, channel):
        """Remove admin privilege from a user. @deadmin <username> <channel>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['user'] = True
            user_doc['role']['op'] = False
            user_doc['role']['admin'] = False
            user_doc['role']['owner'] = False
            del user_doc['channels'][channel]
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User have now been deadmined!")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("owner")
    def cmd_owner(self, user, src_chan, username):
        """Remove admin privilege from a user. @deadmin <username>"""
        coll = self.factory.db.users

        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc['role']['owner'] = True
            user_doc['role']['admin'] = True
            user_doc['role']['op'] = True
            user_doc['role']['user'] = True
            user_doc["all"] = True
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "User now has all privileges.")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("op", 1)
    def cmd_addword(self, user, src_chan, word, channel):
        """Blacklist a word by regexp. @addword <word> <channel>"""

        try:
            self.engine.add(word, channel)
        except Exception as exc:
            log.err(exc)
            self.notice(user.split('!', 1)[0], "An error ocurred")
        else:
            self.notice(user.split('!', 1)[0], "Added word %s" % word)

    @has_permission("op", 1)
    def cmd_delword(self, user, src_chan, word, channel):
        """Delete a word from a blacklist. @delword <word> <channel>"""

        try:
            self.engine.delete(word, channel)
        except Exception as exc:
            log.err(exc)
            self.notice(user.split('!', 1)[0], "An error ocurred")
        else:
            self.notice(user.split('!', 1)[0], "Deleted word %s" % word)

    @has_permission("op", 0)
    def cmd_showwords(self, user, src_chan, channel):
        """Show all blacklisted words for a channel. @showwords <channel>"""

        try:
            words = self.engine.show(channel)
        except Exception as exc:
            log.err(exc)
            self.notice(user.split('!', 1)[0], "An error ocurred")
        else:
            if len(words) > 0:
                self.notice(user.split('!', 1)[0],
                    "Blacklisted words for %s:" % channel)

                for word in words:
                    self.notice(user.split('!', 1)[0],
                        word['word'].encode("utf8"))
            else:
                self.notice(user.split('!', 1)[0],
                    "No blacklisted words for %s." % channel)

    @has_permission("owner")
    def cmd_allchan(self, user, src_chan, username):
        """Allow a user to change lists in all channels. @allchan <username>"""

        coll = self.factory.db.users
        user_doc = coll.find_one({"username": username})

        if user_doc is not None:
            user_doc["all"] = True
            coll.save(user_doc)
            self.notice(user.split('!', 1)[0], "Granted user all permission")
        else:
            self.notice(user.split('!', 1)[0], "User not registered!")

    @has_permission("admin", 1)
    def cmd_set(self, user, src_chan, option, channel=None, *value):
        """Set an option for a channel. @set <option> <channel> <value>"""

        if channel is None:
            self.notice(user.split('!', 1)[0], "No channel specified!")

        coll = self.factory.db.chan_settings
        cs = coll.find_one({"channel": channel})

        if cs is not None:
            if option == "list":
                self.notice(user.split('!', 1)[0], "Channel settings:")

                for setting in cs:
                    if setting == "_id":
                        continue

                    self.notice(user.split('!', 1)[0], "{}: {}".format(setting,
                        cs[setting]))

            elif option in ("kicker", "ban", "private"):
                if value[0] == "on":
                    cs[option] = True
                elif value[0] == "off":
                    cs[option] = False
                else:
                    self.notice(user.split('!', 1)[0],
                        "Invalid argument! Must be 'on' or 'off'.")
                    return

                coll.save(cs)
            elif option in ("ttb", "bantime", "ttk"):
                try:
                    cs[option] = int(value[0])
                except TypeError:
                    self.notice(user.split('!', 1)[0],
                        "Invalid argument! Must be an integer.")
                else:
                    coll.save(cs)
            elif option == "channel":
                self.notice(user.split('!', 1)[0],
                        "Channel cannot be changed!")
                return
            elif option in ("cmd_atb", "cmd_kick", "ban_reason",
                "kick_reason", "chanserv"):
                cs[option] = ' '.join(value)
                coll.save(cs)
            else:
                self.notice(user.split('!', 1)[0], "Invalid option!")
        else:
            self.notice(user.split('!', 1)[0],
                "Channel does not exist in my records.")

    @has_permission("owner")
    def cmd_nick(self, user, src_chan, nick=None):
        """Change nick of the bot. @nick <nick>"""

        if nick:
            self.setNick(nick)