# -*- coding: utf-8 -*-

import pymongo
import re


class Badwords(object):
    """An engine to check text for badwords."""

    def __init__(self, db):
        """Init"""
        self._coll = db.badwords
        self._coll.ensure_index([("word", pymongo.ASCENDING),
            ("channel", pymongo.ASCENDING)])

    def add(self, word, channel):
        """Add a word to database"""
        self._coll.insert({"word": word.strip(), "channel": channel.strip()})

    def delete(self, word, channel):
        """Delete a word from the database"""
        self._coll.remove({"word": word.strip(), "channel": channel.strip()})

    def check(self, channel, msg):
        """Check if any word is found."""
        found = False
        cursor = self._coll.find({"channel": channel})

        for row in cursor:
            if re.search(row['word'], msg, re.I):
                found = True
                break

        return found