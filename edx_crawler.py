#!/usr/bin/env python
# -*- coding: utf-8 -*-

# November 2017. OEDO Analytics Group
#
# Main module for crawling text, quiz and video components using edx-dl downloader. 
# Original source code is modified from: https://github.com/coursera-dl/edx-dl/blob/master/edx_dl/edx_dl.py
#===========================================================================================================

import argparse
import getpass
import json
import logging
import os
import pickle
import re
import sys
import string
import codecs
import subprocess

from webvtt import WebVTT
from datetime import datetime
from functools import partial
from multiprocessing.dummy import Pool as ThreadPool
from bs4 import BeautifulSoup as BeautifulSoup
from six.moves.http_cookiejar import CookieJar
from six.moves.urllib.error import HTTPError, URLError
from six.moves.urllib.parse import urlencode
from six.moves.urllib.request import (
	urlopen,
	build_opener,
	install_opener,
	HTTPCookieProcessor,
	Request,
	urlretrieve,
)

from lib.common import (
	Unit,
	Video,
	ExitCode,
	DEFAULT_FILE_FORMATS,
)

from lib.parsing import (
	edx_json2srt,
	get_page_extractor,
	is_youtube_url,
)

from lib.utils import (
	clean_filename,
	directory_name,
	execute_command,
	get_filename_from_prefix,
	get_page_contents,
	get_page_contents_as_json,
	mkdir_p,
	remove_duplicates,
)

OPENEDX_SITES = {
	'edx': {
		'url': 'https://courses.edx.org',
		'courseware-selector': ('nav', {'aria-label': 'Course Navigation'}),
	}
}

BASE_URL = OPENEDX_SITES['edx']['url']
EDX_HOMEPAGE = BASE_URL + '/login_ajax'
LOGIN_API = BASE_URL + '/login_ajax'
DASHBOARD = BASE_URL + '/dashboard'
COURSEWARE_SEL = OPENEDX_SITES['edx']['courseware-selector']


#Parse the arguments passed to the program on the command line.
def parse_args():
	
	parser = argparse.ArgumentParser(prog='edx-crawler',
									 description='Crawling text from the OpenEdX platform')
	
	# optional arguments
	parser.add_argument('-url',
						'--course-urls',
						dest='course_urls',
						nargs='*',
						action='store',
						required=True,
						help='target course urls'
						'(e.g., https://courses.edx.org/courses/course-v1:TokyoTechX+GeoS101x+2T2016/course/)')

	parser.add_argument('-u',
						'--username',
						dest='username',
						required=True,
						action='store',
						help='your edX username (email)')

	parser.add_argument('-p',
						'--password',
						dest='password',
						action='store',
						help='your edX password'
						'beware: it might be visible to other users on your system')

	parser.add_argument('-d',
						'--html-dir',
						dest='html_dir',
						action='store',
						help='directory to store data',
						default='HTMLs')

	parser.add_argument('-x',
						'--platform',
						dest='platform',
						action='store',	
						help='default is edx platform',
						default='edx')

	parser.add_argument('--filter-section',
						dest='filter_section',
						action='store',
						default=None,
						help='filters sections to be downloaded')

	parser.add_argument('--list-file-formats',
						dest='list_file_formats',
						action='store_true',
						default=False,
						help='list the default file formats extracted')

	parser.add_argument('--file-formats',
						dest='file_formats',
						action='store',
						default=None,
						help='appends file formats to be extracted (comma '
						'separated)')

	parser.add_argument('--overwrite-file-formats',
						dest='overwrite_file_formats',
						action='store_true',
						default=False,
						help='if active overwrites the file formats to be '
						'extracted')

	parser.add_argument('--sequential',
						dest='sequential',
						action='store_true',
						default=False,
						help='extracts the resources from the pages sequentially')

	parser.add_argument('--quiet',
						dest='quiet',
						action='store_true',
						default=False,
						help='omit as many messages as possible, only printing errors')

	parser.add_argument('--debug',
						dest='debug',
						action='store_true',
						default=False,
						help='print lots of debug information')

	args = parser.parse_args()

	# Initialize the logging system first so that other functions
	# can use it right away.
	if args.debug:
		logging.basicConfig(level=logging.DEBUG,
							format='%(name)s[%(funcName)s] %(message)s')
	elif args.quiet:
		logging.basicConfig(level=logging.ERROR,
							format='%(name)s: %(message)s')
	else:
		logging.basicConfig(level=logging.INFO,
							format='%(message)s')

	return args


def _display_courses(courses):
	"""
	List the courses that the user has enrolled.
	"""
	logging.info('You can access %d courses', len(courses))

	for i, course in enumerate(courses, 1):
		logging.info('%2d - %s [%s]', i, course.name, course.id)
		logging.info('     %s', course.url)


def get_courses_info(url, headers):
	"""
	Extracts the courses information from the dashboard.
	"""
	logging.info('Extracting course information from dashboard.')

	page = get_page_contents(url, headers)
	page_extractor = get_page_extractor(url)
	courses = page_extractor.extract_courses_from_html(page, BASE_URL)

	logging.debug('Data extracted: %s', courses)

	return courses


def _get_initial_token(url):
	"""
	Create initial connection to get authentication token for future
	requests.

	Returns a string to be used in subsequent connections with the
	X-CSRFToken header or the empty string if we didn't find any token in
	the cookies.
	"""
	logging.info('Getting initial CSRF token.')

	cookiejar = CookieJar()
	opener = build_opener(HTTPCookieProcessor(cookiejar))
	install_opener(opener)
	opener.open(url)

	for cookie in cookiejar:
		if cookie.name == 'csrftoken':
			logging.info('Found CSRF token.')
			return cookie.value

	logging.warn('Did not find the CSRF token.')
	return ''


def get_available_sections(url, headers):
	"""
	Extracts the sections and subsections from a given url
	"""
	logging.debug("Extracting sections for :" + url)

	page = get_page_contents(url, headers)
	page_extractor = get_page_extractor(url)
	sections = page_extractor.extract_sections_from_html(page, BASE_URL)

	logging.debug("Extracted sections: " + str(sections))
	return sections

def edx_login(url, headers, username, password):
	"""
	Log in user into the openedx website.
	"""
	logging.info('Logging into Open edX site: %s', url)

	post_data = urlencode({'email': username,
						   'password': password,
						   'remember': False}).encode('utf-8')

	request = Request(url, post_data, headers)
	response = urlopen(request)
	resp = json.loads(response.read().decode('utf-8'))
	return resp


def edx_get_headers():
	"""
	Build the Open edX headers to create future requests.
	"""
	logging.info('Building initial headers for future requests.')

	headers = {
		'User-Agent': 'edX-downloader/0.01',
		'Accept': 'application/json, text/javascript, */*; q=0.01',
		'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
		'Referer': EDX_HOMEPAGE,
		'X-Requested-With': 'XMLHttpRequest',
		'X-CSRFToken': _get_initial_token(EDX_HOMEPAGE),
	}

	logging.debug('Headers built: %s', headers)
	return headers


def extract_units(url, headers, file_formats):
	"""
	Parses a webpage and extracts its resources e.g. video_url, sub_url, etc.
	"""
	#logging.info("Processing '%s'", url)

	page = get_page_contents(url, headers)
	page_extractor = get_page_extractor(url)
	units = page_extractor.extract_units_from_html(page, BASE_URL, file_formats)

	return units


def extract_all_units_in_sequence(urls, headers, file_formats):
	"""
	Returns a dict of all the units in the selected_sections: {url, units}
	sequentially, this is clearer for debug purposes
	"""
	logging.info('Extracting all units information in sequentially.')
	logging.debug('urls: ' + str(urls))

	units = [extract_units(url, headers, file_formats) for url in urls]
	all_units = dict(zip(urls, units))

	return all_units


def extract_all_units_in_parallel(urls, headers, file_formats):
	"""
	Returns a dict of all the units in the selected_sections: {url, units}
	in parallel
	"""
	logging.info('Extracting all units information in parallel.')
	logging.debug('urls: ' + str(urls))

	mapfunc = partial(extract_units, file_formats=file_formats, headers=headers)
	pool = ThreadPool(16)
	units = pool.map(mapfunc, urls)
	pool.close()
	pool.join()
	all_units = dict(zip(urls, units))

	return all_units


def _display_sections_menu(course, sections):
	"""
	List the weeks for the given course.
	"""
	num_sections = len(sections)

	logging.info('%s [%s] has %d sections so far', course.name, course.id, num_sections)
	for i, section in enumerate(sections, 1):
		logging.info('%2d - Download %s videos', i, section.name)


def _filter_sections(index, sections):
	"""
	Get the sections for the given index.

	If the index is not valid (that is, None, a non-integer, a negative
	integer, or an integer above the number of the sections), we choose all
	sections.
	"""
	num_sections = len(sections)

	logging.info('Filtering sections')

	if index is not None:
		try:
			index = int(index)
			if index > 0 and index <= num_sections:
				logging.info('Sections filtered to: %d', index)
				return [sections[index - 1]]
			else:
				pass  # log some info here
		except ValueError:
			pass   # log some info here
	else:
		pass  # log some info here

	return sections


def _display_sections(sections):
	"""
	Displays a tree of section(s) and subsections
	"""
	logging.info('Downloading %d section(s)', len(sections))

	for section in sections:
		logging.info('Section %2d: %s', section.position, section.name)
		for subsection in section.subsections:
			logging.info('  %s', subsection.name)


def parse_courses(args, available_courses):
	"""
	Parses courses options and returns the selected_courses.
	"""
	if len(args.course_urls) == 0:
		logging.error('You must pass the URL of at least one course, check the correct url with --list-courses')
		exit(ExitCode.MISSING_COURSE_URL)

	selected_courses = [available_course
						for available_course in available_courses
						for url in args.course_urls
						if available_course.url == url]
	if len(selected_courses) == 0:
		logging.error('You have not passed a valid course url, check the correct url with --list-courses')
		exit(ExitCode.INVALID_COURSE_URL)
	return selected_courses


def parse_sections(args, selections):
	"""
	Parses sections options and returns selections filtered by
	selected_sections
	"""
	if not args.filter_section:
		return selections

	filtered_selections = {selected_course:
						   _filter_sections(args.filter_section, selected_sections)
						   for selected_course, selected_sections in selections.items()}
	return filtered_selections


def parse_file_formats(args):
	"""
	parse options for file formats and builds the array to be used
	"""
	file_formats = DEFAULT_FILE_FORMATS

	if args.list_file_formats:
		logging.info(file_formats)
		exit(ExitCode.OK)

	if args.overwrite_file_formats:
		file_formats = []

	if args.file_formats:
		new_file_formats = args.file_formats.split(",")
		file_formats.extend(new_file_formats)

	logging.debug("file_formats: %s", file_formats)
	return file_formats


def _display_selections(selections):
	"""
	Displays the course, sections and subsections to be downloaded
	"""
	for selected_course, selected_sections in selections.items():
		logging.info('Downloading %s [%s]',
					 selected_course.name, selected_course.id)
		_display_sections(selected_sections)


def parse_units(all_units):
	"""
	Parses units options and corner cases
	"""
	flat_units = [unit for units in all_units.values() for unit in units]
	if len(flat_units) < 1:
		logging.warn('No downloadable video found.')
		exit(ExitCode.NO_DOWNLOADABLE_VIDEO)


def remove_repeated_urls(all_units):
	"""
	Removes repeated urls from the units, it does not consider subtitles.
	This is done to avoid repeated downloads.
	"""
	existing_urls = set()
	filtered_units = {}
	for url, units in all_units.items():
		reduced_units = []
		for unit in units:
			videos = []
			for video in unit.videos:
				# we don't analyze the subtitles for repetition since
				# their size is negligible for the goal of this function
				video_youtube_url = None
				if video.video_youtube_url not in existing_urls:
					video_youtube_url = video.video_youtube_url
					existing_urls.add(video_youtube_url)

				mp4_urls, existing_urls = remove_duplicates(video.mp4_urls, existing_urls)

				if video_youtube_url is not None or len(mp4_urls) > 0:
					videos.append(Video(video_youtube_url=video_youtube_url,
										available_subs_url=video.available_subs_url,
										sub_template_url=video.sub_template_url,
										mp4_urls=mp4_urls))

			resources_urls, existing_urls = remove_duplicates(unit.resources_urls, existing_urls)

			if len(videos) > 0 or len(resources_urls) > 0:
				reduced_units.append(Unit(videos=videos,
										  resources_urls=resources_urls))

		filtered_units[url] = reduced_units
	return filtered_units


def num_urls_in_units_dict(units_dict):
	"""
	Counts the number of urls in a all_units dict, it ignores subtitles from
	its counting.
	"""
	num_urls = 0

	for units in units_dict.values():
		for unit in units:
			for video in unit.videos:
				num_urls += int(video.video_youtube_url is not None)
				num_urls += int(video.available_subs_url is not None)
				num_urls += int(video.sub_template_url is not None)
				num_urls += len(video.mp4_urls)
			num_urls += len(unit.resources_urls)

	return num_urls


def save_urls_to_file(urls, filename):
	"""
	Save urls to file. Filename is specified by the user. The original
	purpose of this function is to export urls into a file for external
	downloader.
	"""
	file_ = sys.stdout if filename == '-' else open(filename, 'w')
	file_.writelines(urls)
	file_.close()


def extract_problem_comp(soup):

    tmp = []
    problem_flag = soup.findAll("div", {"data-block-type": "problem"})  ## filter problem component
    for problem_comp in problem_flag:
        dict_soup = problem_comp.find(attrs={"data-content":True}).attrs    ## search no-html parser part
        txt2html = BeautifulSoup(dict_soup["data-content"],'html.parser')       
        dict_soup["data-content"] = BeautifulSoup(txt2html.prettify(formatter=None),'html.parser') ## restore html parser 
        tmp.append( dict_soup["data-content"])    ## save each problem component in list 
    type_div = []
    text = ''
    for each_problem_content in tmp:
            
        for s in each_problem_content.findAll(['h1','h2','h3','h4','h5','h6','p','label','legend']):     
            text+=s.getText()+" "     
      
        
        ############################ search for type of problem(quiz) ######################################
        #### from obseavation, multichoice & checkbox use the same clase. The difference lie into type of input option
        ####                   fillblank & droplist use the same clase but different subclass
        #### class has two attribute located at the 4th layer ('div'), with attribute ['class'][<class> <subclass>]  
        type_div_tmp = each_problem_content.findAll('div')[4]['class'][0]        
        if type_div_tmp == 'choicegroup':    
            multi_or_check = each_problem_content.findAll('input')[0].attrs['type']
            if multi_or_check == 'checkbox':
                type_div_tmp ='checkbox'
            else:
                type_div_tmp = 'multichoice' 
        elif type_div_tmp == 'inputtype':
            if each_problem_content.findAll('div')[4]['class'][1] == 'option-input':
                type_div_tmp = 'droplist'
            else:
                type_div_tmp = 'fillblank' 
        type_div.append(type_div_tmp)   ### append all list of problem types into type_div
    return text,type_div 
       

def crawl_units(subsection_page):
	unit = []
	#for e_html in subsection_page:
	tmp=[]
	idx = 0
	while tmp is not None:
	  id_name = "seq_contents_"+str(idx)
	  tmp = subsection_page.find("div", {"id": id_name})
	  #print ("tmp: %s\n", tmp)
	  unit.append(tmp)
	  idx = idx + 1 
	unit.remove(None)
	#print (str(idx-1))

	
	return unit




def videolen(yt_link):
	duration_raw = subprocess.check_output(["youtube-dl",yt_link, "--get-duration"])
	timeformat = duration_raw.decode("utf-8").split(':')
	if len(timeformat) == 1:
		duration = int(timeformat[0])
	elif len(timeformat) == 2:
		duration = int(timeformat[0])*60+int(timeformat[1])
	else:
		duration = int(timeformat[0])*3600+int(timeformat[1])*60+ int(timeformat[2])
	return duration

def vtt2json(vttfile):
	t_start_milli = []
	t_end_milli = []
	text = []
	for caption in WebVTT().read(vttfile):
		h,m,s,ms= re.split(r'[\.:]+', caption.start)
		t_start_milli.append(h*3600*1000+m*60*1000+s*1000+ms)
		
		h,m,s,ms= re.split(r'[\.:]+', caption.end)
		t_end_milli.append(h*3600*1000+m*60*1000+s*1000+ms)
		
		text.append(caption.text)
	
	dict_obj = dict({"start":t_start_milli,"end":t_end_milli,"text":text})
	return dict_obj


def YT_transcript(yt_link,key):
	checksub = subprocess.check_output(["youtube-dl",yt_link, "--list-sub"])
	transcript_raw = ''
	if 'has no subtitles' not in checksub.decode('utf-8'):
		lang_ls = list(filter(None, checksub.decode("utf-8").split('Language formats\n')[2].split('\n')))
		for lang in lang_ls:
			if key in lang:
				sub_dl = subprocess.check_output(["youtube-dl", yt_link, "--skip-download", "--write-sub", "--sub-lang", key])
				vttfile = re.sub(r'\n','',sub_dl.decode('utf-8').split('Writing video subtitles to: ')[1])
				transcript_raw = vtt2json(vttfile)
				os.remove(vttfile)
	return transcript_raw

def extract_video_component(args,coursename,headers,soup,section,subsection,unit):	
	
	video_flag = soup.findAll("div", {"data-block-type": "video"})
	video_meta_list = []
	for video_comp in video_flag:
		video_meta = dict()
		txtjson = video_comp.find('div',{"data-metadata":True})['data-metadata']
		txt2dict = json.loads(txtjson)
		yt_id = re.sub(r"1.00:", '', txt2dict['streams'])
		yt_link = 'https://youtu.be/'+ yt_id
		duration = videolen(yt_link)

		video_meta.update({'section': section , 'subsection': subsection, 'unit_idx': unit, 'youtube_url':yt_link, 'video_duration':duration})
		for key, value in txt2dict['transcriptLanguages'].items():
			transcript_name = 'transcript_'+ key
			transcript_url = 'https://courses.edx.org/' + re.sub(r"__lang__",key, txt2dict['transcriptTranslationUrl']) 
			print('download '+ value + ' transcript of '+ yt_link)
			try:
				transcript_dump = get_page_contents(transcript_url, headers)
				transcript_raw = json.loads(transcript_dump)
				#print (transcript_raw)
				video_meta.update({transcript_name:transcript_raw['text']})
			except (HTTPError,URLError) as exception:
				print('     bug: cannot download from edx site')
				transcript_dump = YT_transcript(yt_link,key)
				if len(transcript_dump) == 0:
					print('     no transcript available on YouTube')
					video_meta.update({transcript_name:{"start":'',"end":'',"text":''}})
					logging.warn('transcript (error: %s)', exception)
					errorlog = os.path.join(args.html_dir,coursename,'transcript_error_report.txt')
					f = open(errorlog, 'a')
					text = '---------------------------------\n'\
					+ 'transcript error: ' + str(exception) +'\n' \
					+ 'video url: '+ yt_link +'\n' \
					+ 'language: ' + value + '\n' \
					+ 'section:  ' + section + '\n'\
					+ 'subsection: ' + subsection + '\n'\
					+ 'unit_idx: ' + unit + '\n' \
					+'---------------------------------'
					f.write(text)
					f.close()
				else:
					print('     transcript was successfuly downloaded from YouTube')
					video_meta.update({transcript_name:transcript_dump['text']})

		video_meta_list.append(video_meta)
	return video_meta_list


def save_html_to_file(args, selections, all_urls, headers):

	sub_idx = 0
	prob_type_set = []
	counter_video = 1

	for selected_course, selected_sections in selections.items():
		coursename = directory_name(selected_course.name)
		
		for selected_section in selected_sections:
			section_dirname = "%02d-%s" % (selected_section.position,
										   selected_section.name)
			target_dir = os.path.join(args.html_dir, coursename,
									  clean_filename(section_dirname))
			mkdir_p(target_dir)
			
			for subsection in selected_section.subsections:
			   
				if subsection.name == None:
					subsection.name = 'Untitled'
				target_subdir = os.path.join(target_dir, clean_filename(subsection.name))
				mkdir_p(target_subdir)
				logging.info('url: '+ str(all_urls[sub_idx]) + ', subsection: ' + str(subsection.name))
				page = get_page_contents(str(all_urls[sub_idx]), headers)
				#print ("Contents!\n")
				soup = BeautifulSoup(page, "html.parser")

				#div contains all units (seq_contents_#)
				main_content=soup.find("div", {"class": "container"})

				units = crawl_units(main_content)
				counter = 0
				sub_idx = sub_idx+1

				for unit in units:
					
					filename_template = "seq_contents_"+str(counter) +".html"
					filename = os.path.join(target_subdir, filename_template)

					filename_template_txt = "seq_contents_"+str(counter) +".txt"
					filename_txt = os.path.join(target_subdir, filename_template_txt)

					filename_template_prob_txt = "seq_contents_"+str(counter) +"_prob.txt"
					filename_prob_txt = os.path.join(target_subdir, filename_template_prob_txt)

					filename_template_video_json = "seq_contents_"+str(counter) +"_vdo.json"
					filename_video_json = os.path.join(target_subdir, filename_template_video_json)



					logging.info('path: '+ str(target_subdir) + ', filename: ' + str(filename))

					try:
						file_ = sys.stdout if filename == '-' else codecs.open( filename, 'w', 'utf-8')
					except IOError as exc:
						f = open('downloading_error_report.txt', 'a')
						text = 'External command error ignored: ' +str(exc) + '\n\n'
						f.write(text)
						f.close()
						file_ = sys.stdout if filename == '-' else codecs.open( filename_template, 'w', 'utf-8')
					
					file_.writelines(unit.prettify(formatter=None))
					file_.close()

					soup =unit.prettify(formatter=None)
					soup = BeautifulSoup(soup, "html.parser")
					
					# select only html componert (disregard video, problem)
					html_flag = soup.findAll("div", {"data-block-type": "html"})
					if len(html_flag) > 0:
					
						#create file only when html component exists
						file_txt = sys.stdout if filename_txt == '-' else codecs.open( filename_txt, 'w', 'utf-8')
						text=""
						for soup_component in html_flag:					
							for s in soup_component.findAll(['h1','h2','h3','h4','h5','h6','p','li']):
								text+=s.getText()+" "                               		

						file_txt.writelines(text)
						file_txt.close()
						print(filename_txt + ' of text component was created')

					# select only problem componert (disregard video, text)
					prob_txt,prob_types = extract_problem_comp(soup)
					
					if len(prob_txt) > 0:
						file_prob_txt = sys.stdout if filename == '-' else codecs.open( filename_prob_txt, 'w', 'utf-8')
						for prob_type in prob_types:
							prob_type_set.append(prob_type+' \n')
						
						file_prob_txt.writelines(prob_txt)
						file_prob_txt.close()
						print(filename_prob_txt + ' of problem component was created')

					tmp_video_dict = extract_video_component(args,coursename,headers,soup,clean_filename(section_dirname),clean_filename(subsection.name),"seq_contents_"+str(counter))
					if len(tmp_video_dict) > 0:
						file_video_json = sys.stdout if filename == '-' else codecs.open( filename_video_json, 'w', 'utf-8')
						video_unit_dict = dict()
						for vd in tmp_video_dict:
							video_unit_dict.update({"video_block_"+str(counter_video).zfill(2):vd})
							counter_video +=1
						video_dict2json = json.dumps(video_unit_dict, sort_keys=False, indent=4, separators=(',', ': '))
						file_video_json.writelines(video_dict2json)
						file_video_json.close()
						print(filename_video_json + ' of video component was created')
						

					counter += 1

	save_urls_to_file(prob_type_set,  os.path.join(args.html_dir, coursename,  "all_prob_type.txt"))
	

def main():

	start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	args = parse_args()
	file_formats = parse_file_formats(args)

	# Query password, if not alredy passed by command line.
	if not args.password:
		args.password = getpass.getpass(stream=sys.stderr)

	if not args.username or not args.password:
		logging.error("You must supply username and password to log-in")
		exit(ExitCode.MISSING_CREDENTIALS)

	# Prepare Headers
	headers = edx_get_headers()

	# Login
	resp = edx_login(LOGIN_API, headers, args.username, args.password)
	if not resp.get('success', False):
		logging.error(resp.get('value', "Wrong Email or Password."))
		exit(ExitCode.WRONG_EMAIL_OR_PASSWORD)

	# Parse and select the available courses
	courses = get_courses_info(DASHBOARD, headers)
	available_courses = [course for course in courses if course.state == 'Started']
	selected_courses = parse_courses(args, available_courses)

	# Parse the sections and build the selections dict filtered by sections
	if args.platform == 'edx':
		all_selections = {selected_course:
						  get_available_sections(selected_course.url.replace('info', 'course'), headers)
						  for selected_course in selected_courses}
	else:
		all_selections = {selected_course:
						  get_available_sections(selected_course.url.replace('info', 'courseware'), headers)
						  for selected_course in selected_courses}

	selections = parse_sections(args, all_selections)
	_display_selections(selections)

	# Extract the unit information (downloadable resources)
	# This parses the HTML of all the subsection.url and extracts
	# the URLs of the resources as Units.
	all_urls = [subsection.url
				for selected_sections in selections.values()
				for selected_section in selected_sections
				for subsection in selected_section.subsections]

	extractor = extract_all_units_in_parallel
	if args.sequential:
		extractor = extract_all_units_in_sequence

	all_units = extractor(all_urls, headers, file_formats)

	parse_units(selections)

	# This removes all repeated important urls
	# FIXME: This is not the best way to do it but it is the simplest, a
	# better approach will be to create symbolic or hard links for the repeated
	# units to avoid losing information
	filtered_units = remove_repeated_urls(all_units)
	num_all_urls = num_urls_in_units_dict(all_units)
	num_filtered_urls = num_urls_in_units_dict(filtered_units)
	logging.warn('Removed %d duplicated urls from %d in total',
				 (num_all_urls - num_filtered_urls), num_all_urls)

	#saving html contebt as course unit
	save_html_to_file(args, selections, all_urls, headers)
	

if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt:
		logging.warn("\n\nCTRL-C detected, shutting down....")
		sys.exit(ExitCode.OK)
