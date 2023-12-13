# -*- Code created August 2023. Olivier Simard-Hanley. -*-
# this is the main file for the a working eink dashboard, adapted from DispatchPi.


# TODO
# ajouter heure à date en haut
# réduire taile titres list calendrier 
# remplacer icônes humidité
# changer aqi par UV (avec icône)
# intégrer AQI dans prévisions


import os
import flask
from flask import send_file
import requests
import json
import datetime
from io import BytesIO
from itertools import islice

#google libraries
import google_auth_oauthlib.flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

#local functions

from gmail_connector import GmailConnector
from google_calendar import GCalConnector
from eink_image import Image_transform
from svg_updater import SVGFile
from get_weather import GetEnviroCanWeather
from google_tasks import GtasksConnector

##SECRETS  - change the file paths as needed

#Path to your API credentials file
CLIENT_SECRETS_FILE = "secrets/api_credentials.json"
#Path to your API Access token file
TOKEN_FILE_GMAIL = 'secrets/token_gmail.json'
TOKEN_FILE_GTASKS = 'secrets/token_gtasks.json'
TOKEN_FILE_GCALENDAR = 'secrets/token_gcalendar.json'

# Import ENV variables
# Load JSON data from a file
with open('secrets/config.json', 'r', encoding='utf-8') as file:
    config_data = json.load(file)

# Extract variables
GOOGLE_TASKS_LIST_ID = config_data.get('GOOGLE_TASKS_LIST_ID')
GOOGLE_CALENDAR_ID = config_data.get('GOOGLE_CALENDAR_ID')
SCOPES_GMAIL = config_data.get('SCOPES', {}).get('GMAIL', ['https://www.googleapis.com/auth/gmail.readonly'])
SCOPES_GTASKS = config_data.get('SCOPES', {}).get('GTASKS', ['https://www.googleapis.com/auth/tasks.readonly'])
SCOPES_GCALENDAR = config_data.get('SCOPES', {}).get('GCALENDAR', ['https://www.googleapis.com/auth/calendar.readonly'])


# Extract the coordinate string, split it by comma, and convert each part to float
coord_string = config_data.get('WEATHER_COORDINATES', '0.0, 0.0')
try:
    latitude, longitude = map(float, coord_string.split(','))
    WEATHER_COORDINATES = (latitude, longitude)
except ValueError:
    raise ValueError("Invalid format for WEATHER_COORDINATES. Must be two float values separated by a comma.")

##AUTH

# This OAuth 2.0 access scope allows to read emails
SCOPES_GMAIL = ['https://www.googleapis.com/auth/gmail.readonly']
SCOPES_GTASKS = ['https://www.googleapis.com/auth/tasks.readonly']
SCOPES_GCALENDAR = ['https://www.googleapis.com/auth/calendar.readonly']

## FLASK APP
app = flask.Flask(__name__)
app.secret_key= config_data.get('FLASK_KEY', '101')

## FUNCTIONS

def fetch_grocery_list():
    if os.path.exists(TOKEN_FILE_GTASKS):
        credentials = generate_credentials(token_file=TOKEN_FILE_GTASKS, scopes=SCOPES_GTASKS)
    else:
        flask.session['token_file'] = TOKEN_FILE_GTASKS
        flask.session['scopes'] = SCOPES_GTASKS
        flask.session["client_secret_file"] = CLIENT_SECRETS_FILE
        return flask.redirect('authorize')
    
    Google_tasks = GtasksConnector(creds=credentials)
    # Google_tasks.get_lists() # Run to see the available task lists in your account
    grocery_items = Google_tasks.get_tasks(tasklist_id=GOOGLE_TASKS_LIST_ID) # Fetch a specific task list
    
    return grocery_items


def fetch_image_from_gmail():
  #update refresh token if we have a token file
  if os.path.exists(TOKEN_FILE_GMAIL):
    credentials = generate_credentials(token_file=TOKEN_FILE_GMAIL, scopes=SCOPES_GMAIL)
  
  #if there are no credentials, redirect to the authorization flow 
  else:
    # keep the current token file and scopes in session memory
    flask.session['token_file'] = TOKEN_FILE_GMAIL
    flask.session['scopes'] = SCOPES_GMAIL
    flask.session["client_secret_file"] = CLIENT_SECRETS_FILE
    return flask.redirect('authorize')

  # initialize Gmail connector
  gmail_inbox =  GmailConnector(creds=credentials)

  # pull attachments (num_emails looks at the X most recent emails to be sure we intercept an attachment)
  gmail_inbox.pull_attachments(userID='me', num_emails=3)

  # get the image to send
  image_to_send, output_text = gmail_inbox.grab_first_image(userID = 'me')
 
  # prepare bytes stream
  output_stream = BytesIO()
  #transform image into a low res format for the eink screen
  transformed_image = Image_transform(path_or_image=image_to_send)
  transformed_image.save(output_path_or_stream = output_stream)
    
  # display the image (don't cache it)
  # output.seek resets the pointer to the beginning of the file 
  output_stream.seek(0)
  
  return send_file(output_stream, mimetype="image/png")

def fetch_weather():
  weather_service = GetEnviroCanWeather(WEATHER_COORDINATES)
  return weather_service.get_curr_weather_and_two_next_periods()

def fetch_calendar_events():

  if os.path.exists(TOKEN_FILE_GCALENDAR):
      credentials = generate_credentials(token_file=TOKEN_FILE_GCALENDAR, scopes=SCOPES_GCALENDAR)
  else:
      flask.session['token_file'] = TOKEN_FILE_GCALENDAR
      flask.session['scopes'] = SCOPES_GCALENDAR
      flask.session["client_secret_file"] = CLIENT_SECRETS_FILE
      return flask.redirect('authorize')
  
  weather_service = GetEnviroCanWeather(WEATHER_COORDINATES)   # Get local timezone from weather service
  local_timezone_str = weather_service.get_timezone()

  google_calendar = GCalConnector(creds = credentials, local_timezone_str= local_timezone_str, calendar_id=GOOGLE_CALENDAR_ID)
  #google_calendar.get_calendars_list() # Run to print the available calendars in your account

  return google_calendar.get_calendar_events()


def generate_credentials(token_file, scopes):
  #if there are stored credentials, retrieve them
  credentials = Credentials.from_authorized_user_file(token_file, scopes)
  
  #if credentials are expired, refresh
  if not credentials.valid:
    credentials.refresh(Request())

    #Save credentials to file if they were refreshed 
    with open(token_file, 'w') as token:
      token.write(credentials.to_json())

  return credentials

def take_from_dict(n, iterable):
    """Return the first n items of the iterable as a list."""
    return list(islice(iterable, n))

  
## APP STARTS HERE

# draw the index
@app.route('/')
def index():

  return ('<table>' + 
          "<tr><td><a href='/display_gmail_image''>See the image pulled from Gmail</a></td>" +
          "<tr><td><a href='/display_calendar_events''>See your upcoming Google Calendar events</a></td>" +
          "<tr><td><a href='/display_grocery_list''>See the Google Tasks grocery list</a></td>" +
          "<tr><td><a href='/dashboard_homepage''>See dashboard homepage</a></td>" +    
          "<tr><td><a href='/weather_output''>See weather output</a></td>" +                
          '<tr><td><a href="/authorize">Test the auth flow directly (gmail by default). You will be sent back to the index</a></td>' +
          '<tr><td><a href="/revoke">Revoke current credentials</a></td>' +
          '</td></tr></table>')

# display grocery list fetched from Google Tasks
@app.route('/display_grocery_list')
def api_route_grocery_list():
  return fetch_grocery_list()

# display grocery list fetched from Google Calendar
@app.route('/display_calendar_events')
def api_route_calendar_events():
  return fetch_calendar_events()

# display weather output fetched from Weather Canada
@app.route('/weather_output')
def weather_output():

  current_weather, forecast_period_1, forecast_period_2, alerts = fetch_weather()
    
  return(f'{current_weather, forecast_period_1, forecast_period_2, alerts}')
  # return(f'{pretty_output}')

# display dashboard homepage
@app.route('/dashboard_homepage')
def draw_homepage():

  # Get weather
  current_weather_dict, forecast_1_period_dict, forecast_period_2_dict, alerts = fetch_weather()

  # Get grocery list
  grocery_items = {"grocery_list" : fetch_grocery_list()}

  # Get calendar items
  calendar_items = {"calendar_events" : fetch_calendar_events()}

  final_svg = SVGFile(template_svg_filepath="svg_final.svg", output_filename= "svg_output.svg")
  final_svg.update_svg(current_weather_dict = current_weather_dict, forecast_1_period_dict = forecast_1_period_dict, 
                       forecast_period_2_dict = forecast_period_2_dict, grocery_dict = grocery_items, calendar_dict = calendar_items)
  output = final_svg.send_to_pi()
  
  return send_file(output, mimetype="image/png")


# display image pulled from gmail
@app.route('/display_gmail_image')
def api_route_gmail_image():

  return fetch_image_from_gmail()


# build the authorization flow
@app.route('/authorize')
def authorize():

  # if no token file stored in session, assume we are testing gmail
  if 'token_file' not in flask.session:
    flask.session['token_file'] = TOKEN_FILE_GMAIL
    flask.session['scopes'] = SCOPES_GMAIL
    flask.session["client_secret_file"] = CLIENT_SECRETS_FILE
    
  #if we are just testing the auth flow and the credentials are expired, simply refresh them
  if os.path.exists(flask.session['token_file']):
      credentials = Credentials.from_authorized_user_file(flask.session['token_file'], flask.session['scopes'])
      if not credentials.valid:
          credentials.refresh(Request())

          #Save credentials to file if they were refreshed
          with open(flask.session['token_file'], 'w') as token:
              token.write(credentials.to_json())

      return flask.redirect(flask.url_for('index'))
    
  #otherwise fetch the full creds
  else: 
      # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
      flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
          flask.session["client_secret_file"], scopes=flask.session["scopes"])

      # The URI created here must exactly match one of the authorized redirect URIs
      # for the OAuth 2.0 client, which you configured in the API Console. If this
      # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
      # error.
      flow.redirect_uri = flask.url_for('oauth2callback', _external=True)
    
      authorization_url, state = flow.authorization_url(
          # Enable offline access so that you can refresh an access token without
          # re-prompting the user for permission. Recommended for web server apps.
          access_type='offline',
          # Enable incremental authorization. Recommended as a best practice.
          include_granted_scopes='false')
    
      # Store the state so the callback can verify the auth server response.
      flask.session['state'] = state

      return flask.redirect(authorization_url)

# define the callback
@app.route('/oauth2callback')
def oauth2callback():
  # Specify the state when creating the flow in the callback so that it can
  # verified in the authorization server response.
  state = flask.session['state']

  flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      flask.session["client_secret_file"], scopes=flask.session["scopes"], state=state)
  flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

  # Use the authorization server's response to fetch the OAuth 2.0 tokens.
  authorization_response = flask.request.url
  flow.fetch_token(authorization_response=authorization_response)

  # Store credentials in the session.
  credentials = flow.credentials
 
  #save the credentials to file
  with open(flask.session['token_file'], 'w') as token:
      token.write(credentials.to_json())

  return flask.redirect(flask.url_for('index'))

#revoke the credentials : remove the app from authorized apps
#this will reset the refresh token, you'll have to erase the token file to start over
@app.route('/revoke')
def revoke():

  credentials = Credentials.from_authorized_user_file(flask.session['token_file'], flask.session['scopes'])

  revoke = requests.post('https://oauth2.googleapis.com/revoke',
      params={'token': credentials.token},
      headers = {'content-type': 'application/x-www-form-urlencoded'})

  status_code = getattr(revoke, 'status_code')
  if status_code == 200:
    return('Credentials successfully revoked.' + index())
    
  else:
    return('An error occurred.' + index())

if __name__ == '__main__':
  #   When running locally, disable OAuthlib's HTTPs verification.
  #   When running in production *do not* leave this option enabled.
  os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

   #Specify a hostname and port that are set as a valid redirect URI
   #for your API project in the Google API Console.
   #set debug to true when testing locally
  app.run('localhost', 8080, debug=True)

else:
  # When running online, use HTTPS for URLs
  # The lines below should be disabled if you are testing the code locally
  # This is handled by the if name == main block above
  class ReverseProxied(object):
      def __init__(self, app):
          self.app = app

      def __call__(self, environ, start_response):
          scheme = environ.get('HTTP_X_FORWARDED_PROTO')
          if scheme:
              environ['wsgi.url_scheme'] = scheme
          return self.app(environ, start_response)
          
  app.wsgi_app = ReverseProxied(app.wsgi_app)

