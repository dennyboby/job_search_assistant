from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import google.generativeai as palm
from linkedin_api import Linkedin
import PyPDF2, pdfplumber
import argparse
import yaml
import time

class JobDetail():
    def __init__(self, job_id, job_title, job_description, job_link, company_name):
        self.job_id = job_id
        self.job_title = job_title
        self.job_description = job_description
        self.job_link = job_link
        self.company_name = company_name
        self.match_percentage = 0

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
            getattr(other, 'job_title', None) == self.job_title and
            getattr(other, 'company_name', None) == self.company_name)

    def __hash__(self):
        return hash(self.job_title + self.company_name)
    
    def __str__(self):
        # print(self.job_description)
        return "Job title:= %s, Company name:- %s, Job ID:= %s, Match Percentage:= %d" % (self.job_title, self.company_name,\
                                                                                           self.job_id, int(self.match_percentage))

class JobSearchAssistant:
    def __init__(self, dict_args):
        # Initialize the variables
        self.dict_args = dict_args
        self.api = Linkedin(dict_args['email_ID'], dict_args['email_pass'])
        self.job_details = []
        self.resume_text = self.get_resume_text(dict_args['resume_path'])
        self.urn_id = self.api.get_profile(public_id=dict_args['sent_to_public_ID'])['entityUrn'].split(':')[3]
        self.conversation_urn_id = self.api.get_conversation_details(self.urn_id)['dashEntityUrn'].split(':')[3]
        palm.configure(api_key=dict_args['palm_api_key'])
        models = [m for m in palm.list_models() if 'generateText' in m.supported_generation_methods]
        self.model = models[0].name

    # def description_match_percentage(self, job_description, resume_text):
    #     match_set=[job_description, resume_text]
    #     cv=CountVectorizer()
    #     count_matrix=cv.fit_transform(match_set)
    #     match_percentage=cosine_similarity(count_matrix)[0][1]*100
    #     match_percentage=round(match_percentage,2)
    #     return match_percentage 
        
    def description_match_percentage(self, job_description, resume_text):
        query = "Job Description: " + job_description + " Resume: " + resume_text
        query = query + 'What is the resume to job description match percentage? Answer in percentage.'
        completion = palm.generate_text(
                            model=self.model,
                            prompt=query,
                            temperature=0,
                            # The maximum length of the response
                            max_output_tokens=800,)
        print('Match % = ' + completion.result)
        value = completion.result
        value = value.replace('%', '')
        return float(value)
    
    def get_resume_text(self, resume_path):
        with open(resume_path, 'rb') as cv_file:
            reader = PyPDF2.PdfReader(cv_file)
            pages = len(reader.pages)

            script = []
            with pdfplumber.open(cv_file) as pdf:
                for i in range(pages):
                    page = pdf.pages[i]
                    text = page.extract_text()
                    script.append(text)
            script = ''.join(script)
            cv_clear = script.replace("\n", " ")
        # print(cv_clear)
        return cv_clear

    def filter_details(self, jobs, exclude_description_words):
        filtered_jobs = []
        for job in jobs:
            completion = palm.generate_text(
                            model=self.model,
                            prompt=job.job_description + ' Does the above job require green card or US citizenship? Answer only True or False.',
                            temperature=0,
                            # The maximum length of the response
                            max_output_tokens=800,)
            if completion.result == 'False':
                filtered_jobs.append(job)
            #     print('Job ID False : ', job.job_id)
            # else:
            #     print('Completion result: ', completion.result)
            #     print('Job ID True : ', job.job_id)

        return filtered_jobs
        # for job in jobs:
        #     if not any(map(lambda w: w.lower() in job.job_description.lower(), exclude_description_words)):
        #         filtered_jobs.append(job)
        # return filtered_jobs

    def get_jobs(self):
        # Search for jobs
        jobs = self.api.search_jobs(keywords=self.dict_args['keywords'], experience=self.dict_args['experience'], 
                       job_type= self.dict_args['job_type'], 
                       location_name=self.dict_args['location_name'], remote=self.dict_args['remote'], 
                       listed_at=self.dict_args['listed_at'] * 60 * 60, limit=self.dict_args['jobs_limit'])
        print('Total jobs found initial: ', len(jobs))
        # Filter jobs by title
        jobs_filtered = self.filter_job_title(jobs, self.dict_args['include_title_words'], self.dict_args['exclude_title_words'])
        print('Total jobs found after title filter: ', len(jobs_filtered))
        # Get job details
        jobs_details = self.get_job_details(jobs_filtered)
        print('Total jobs found after getting job details: ', len(jobs_details))
        # Filter jobs by company
        jobs_details_filtered = self.filter_companies(jobs_details, self.dict_args['company_blacklist'])
        print('Total jobs found after company filter: ', len(jobs_details_filtered))
        jobs_details_filtered = self.filter_details(jobs_details_filtered, self.dict_args['exclude_description_words'])
        print('Total jobs found after details filter: ', len(jobs_details_filtered))
        # Filter jobs by description
        jobs_filtered = []
        for job in jobs_details_filtered:
            job.match_percentage = self.description_match_percentage(job.job_description, self.resume_text)
            if job.match_percentage >= self.dict_args['job_match_percentage']:
                jobs_filtered.append(job)
        jobs_details_filtered = jobs_filtered
        print('Total jobs found after percentage match filter: ', len(jobs_details_filtered))
        return jobs_details_filtered
        

    def send_message(self, text):
        if self.api.send_message(message_body=text, conversation_urn_id=self.conversation_urn_id):
            print("Could not send message.")

    def filter_job_title(self, jobs, include_title_words, exclude_title_words):
        filtered_jobs = []
        for job in jobs:
            if all(map(lambda w: w.lower() in job['title'].lower(), include_title_words)):
                if not any(map(lambda w: w.lower() in job['title'].lower(), exclude_title_words)):
                    filtered_jobs.append(job)
        return filtered_jobs
    
    def get_job_details(self, jobs):
        # Get job details
        job_details = set()
        for job in jobs:
            job_id = job['trackingUrn'].split(':')[3]
            job_title = job['title']
            job_info = self.api.get_job(job_id)
            job_description = job_info['description']['text']
            job_description = job_description.replace("\n", " ")
            # print(job_description)
            job_link = 'https://www.linkedin.com/jobs/view/' + job_id
            company_name = list(job_info['companyDetails'].values())[0]['companyResolutionResult']['name']
            job_details.add(JobDetail(job_id, job_title, job_description, job_link, company_name))
        return list(job_details)

    def filter_companies(self, jobs, company_blacklist):
        filtered_jobs = []
        for job in jobs:
            if not any(map(lambda w: w.lower() in job.company_name.lower(), company_blacklist)):
                filtered_jobs.append(job)
        return filtered_jobs

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml_path",
                        type=str,
                        default="config.yaml",
                        help="yaml path for the run")

    args = parser.parse_args()
    return args

def load_yaml(yaml_path):
    dict_args = {}
    with open(yaml_path, 'r') as stream:
        dictionary = yaml.safe_load(stream)
        for key, val in dictionary.items():
            dict_args[key] = val
    return dict_args

def main():
    # Initialize the variables
    loop_flag = True
    args = parse_args()
    dict_args = load_yaml(args.yaml_path)
    assistant = JobSearchAssistant(dict_args)

    while loop_flag:
        jobs = assistant.get_jobs()
        print('Total jobs found: ', len(jobs))

        # assistant.send_message('Total jobs found: ' + str(len(jobs)))
        for job in jobs:
            print(job)
            # assistant.send_message(job.job_link)

        # Wait for schedule time
        time.sleep(dict_args['schedule_time'] * 60 * 60)

        if bool(dict_args['schedule_time']) == False:
            loop_flag = False



if __name__ == '__main__':
    main()