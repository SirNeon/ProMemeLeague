from datetime import datetime
import logging
from operator import getitem, itemgetter
import os
import sqlite3 as db
from sys import exit, stderr
import praw
from praw.errors import *
from requests.exceptions import HTTPError
from simpleconfigparser import simpleconfigparser


def add_msg(msg=None, newline=False):
	"""
	Print terminal output to check progress. Give it the message
	to print. Additional newline is optional.
	"""

	if(verbose):
		if msg is not None:
			print msg

		if(newline):
			print '\n'


# make sure this necessary file exists
if(os.path.isfile("players.txt") == False):
	print "Could not find players.txt. Exiting..."
	exit(1)

if(os.path.isfile("teams.txt") == False):
	print "Could not find teams.txt. Exiting..."
	exit(1)

if(os.path.isfile("settings.cfg") == False):
	print "Could not find settings.cfg. Exiting..."
	exit(1)

config = simpleconfigparser()

# check this file for settings
config.read("settings.cfg")

# add terminal output
verbose = config.main.getboolean("verbose")

# get this many comments at a time
scrapeLimit = int(config.main.scrapeLimit)

# enable error logging
errorLogging = config.logging.getboolean("errorLogging")

if(errorLogging):
    logging.basicConfig(
        filename="pmlbot_logerr.log", 
        filemode='a', format="%(asctime)s\nIn "
        "%(filename)s (%(funcName)s:%(lineno)s): "
        "%(message)s", datefmt="%Y-%m-%d %H:%M:%S", 
        level=logging.ERROR, stream=stderr)

username = config.login.username
password = config.login.password

add_msg("Logging in...")

client = praw.Reddit(user_agent="PML stats bot by /u/SirNeon")
client.login(username, password)

playerList = []
teamsList = []

# submission IDs for each team
teamDict = {
	"[TMC]": "2bzehq", "[TTS]": "2bzek6", "[PFC]": "2bzem5", 
	"[NMM]": "2bzesd", "[JTD]": "2bzeud", "[LAD]": "2bzf30", 
	"[TNR]": "2bzf59", "[MRG]": "2bzfac", "[RPM]": "2bzfea", 
	"[SUS]": "2bzffq", 
}

# put the file content into a list
with open("players.txt", 'r') as f:
	for user in f.readlines():
		user = user.strip('\n')
		playerList.append(user)

with open("teams.txt", 'r') as f:
	for team in f.readlines():
		team = team.strip('\n')
		teamsList.append(team)

# connect to the database
con = db.connect("PML.db")
cur = con.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS stats(Team TEXT, CommentID TEXT, User TEXT, Score INT)")

while True:
	# go through the list of players to get data
	for i, user in enumerate(playerList):
		try:
			add_msg("Scanning user {0} / {1}...".format(i + 1, len(playerList)))
			comments = client.get_redditor(user).get_comments(limit=scrapeLimit)

		except (HTTPError, Exception) as e:
			print e
			logging.error(str(e) + "\n\n")
			continue

		for comment in comments:
			try:
				commentBody = str(comment.body)

			except (AttributeError, UnicodeEncodeError):
				continue

			commentBody = commentBody.upper()

			# +PML triggers the bot
			if "+PML" in commentBody:
				add_msg("Bot was triggered. Processing...")

				# check to see if a team was mentioned
				for team in teamsList:
					add_msg("Checking for team...")
					if team in commentBody:
						add_msg("Checking which score to grab...")
						# grab the comment score
						if "[C]" in commentBody:
							add_msg("Grabbing comment score...")

							try:
								commScore = int(comment.score)
								commAuthor = str(comment.author)
								commID = str(comment.id)

							except AttributeError:
								continue

							cur.execute("SELECT Score FROM stats WHERE CommentID=?", (commID,))

							# check to see if the comment has been 
							# scanned before
							if cur.fetchone() is not None:
								cur.execute("UPDATE stats SET Score=? WHERE CommentID=?", (commScore, commID))

							else:
								cur.execute("INSERT INTO stats VALUES(?, ?, ?, ?)", (team, commID, commAuthor, commScore))

							break

						# grab the submission score
						elif "[P]" in commentBody:
							add_msg("Grabbing submission score...")

							try:
								submissionID = str(comment.link_id)
								commID = str(comment.id)

							except AttributeError:
								continue

							submission = client.get_info(thing_id=submissionID)

							try:
								subScore = int(submission.score)
								commAuthor = str(comment.author)

							except AttributeError:
								continue

							cur.execute("SELECT Score FROM stats WHERE CommentID=?", (commID,))

							if cur.fetchone() is not None:
								cur.execute("UPDATE stats SET Score=? WHERE CommentID=?", (subScore, commID))

							else:
								cur.execute("INSERT INTO stats VALUES(?, ?, ?, ?)", (team, commID, commAuthor, subScore))

							break

						# this should only happen if the user didn't 
						# tell the bot what to do correctly
						else:
							break

	con.commit()

	for team in teamsList:
		add_msg("Updating posts...")

		# grab the team's corresponding submission
		submission = client.get_submission(submission_id=teamDict[team])

		# start the post
		bodyContent = "Last updated {0}\n\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
		bodyContent += "| Player | Points |\n"
		bodyContent += "|:------|------:|\n"

		userList = []
		tuppleList = []

		cur.execute("SELECT User FROM stats WHERE Team=?", (team,))

		# grab the users for the team
		for user in cur:
			if user not in userList:
				userList.append(user)

		add_msg("Tallying points...")
		
		for user in userList:
			pointsList = []

			cur.execute("SELECT Score FROM stats WHERE User=?", user)

			# tally the user's points
			for row in cur:
				points = getitem(row, 0)
				pointsList.append(int(points))

			user = getitem(user, 0)
			score = sum(pointsList)

			add_msg("{0}: {1}".format(user, score))

			tuppleList.append((user, score))

		# sort the players by points highest to lowest
		tuppleList.sort(key=itemgetter(1), reverse=True)

		add_msg(tuppleList)

		add_msg("Formatting post...")

		for item in tuppleList:
			user = getitem(item, 0)
			score = getitem(item, 1)

			add_msg("{0}: {1}".format(user, score))

			# further format the post
			bodyContent += "|/u/{0}|{1}|\n".format(user, score)

		add_msg("Submitting results...")

		# submit the edit
		submission.edit(bodyContent)
