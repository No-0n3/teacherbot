# teacherbot
An IRC-Bot based on Twisted that will help you keep your channels free from bad language.

The bot uses a mongodb database for storing information.

Changelog 2015-03-20:
At this moment it has only the authentication system for the bot ready where that works as a single sign-on. It stores the passwords of users as sha512 for security reasons. To avoid bot-takeovers it clears userdata when he quits the network. Basic irc commands are implemented and nickname registration if someone want to run any commands that has a certain permission level.
