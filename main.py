from linkedin_api import Linkedin
import yaml
import argparse
import time

class JobDetail():
    def __init__(self, job_id, job_title, job_description, job_link, company_name):
        self.job_id = job_id
        self.job_title = job_title
        self.job_description = job_description
        self.job_link = job_link
        self.company_name = company_name

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
            getattr(other, 'job_title', None) == self.job_title and
            getattr(other, 'company_name', None) == self.company_name)

    def __hash__(self):
        return hash(self.job_title + self.company_name)
    
    def __str__(self):
        return "Job title:= %s, Company name:- %s, Job ID:= %s" % (self.job_title, self.company_name, self.job_id)

class JobSearchAssistant:
    def __init__(self, dict_args):
        # Initialize the variables
        self.dict_args = dict_args
        self.api = Linkedin(dict_args['email_ID'], dict_args['email_pass'])
        self.job_details = []
        self.include_title_words = dict_args['include_title_words']
        self.company_blacklist = dict_args['company_blacklist']
        self.urn_id = self.api.get_profile(public_id=dict_args['sent_to_public_ID'])['entityUrn'].split(':')[3]
        self.conversation_urn_id = self.api.get_conversation_details(self.urn_id)['dashEntityUrn'].split(':')[3]

    
    def get_jobs(self):
        # Search for jobs
        jobs = self.api.search_jobs(keywords=self.dict_args['keywords'], experience=self.dict_args['experience'], 
                       job_type= self.dict_args['job_type'], 
                       location_name=self.dict_args['location_name'], remote=self.dict_args['remote'], 
                       listed_at=self.dict_args['listed_at'])
        
        # Filter jobs by title
        jobs_filtered = self.filter_job_title(jobs, self.dict_args['include_title_words'], self.dict_args['exclude_title_words'])

        # Get job details
        jobs_details = self.get_job_details(jobs_filtered)

        # Filter jobs by company
        jobs_details_filtered = self.filter_companies(jobs_details, self.dict_args['company_blacklist'])

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
    
    args = parse_args()
    dict_args = load_yaml(args.yaml_path)
    assistant = JobSearchAssistant(dict_args)

    jobs = assistant.get_jobs()
    print('Total jobs found: ', len(jobs))

    assistant.send_message('Total jobs found: ' + str(len(jobs)))
    for job in jobs:
        print(job)
        assistant.send_message(job.job_link)
    assistant.send_message('Are there any issues with the above listed jobs?')


if __name__ == '__main__':
    main()