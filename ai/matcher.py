"""
AI Job-Candidate Matching Engine
Uses TF-IDF vectorization and cosine similarity to match candidates to jobs
Includes bias mitigation, skill gap analysis, and match explanations
"""

import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter


class JobMatcher:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=5000,
            ngram_range=(1, 2)  # Use unigrams and bigrams
        )
        self.is_fitted = False
        self.job_vectors = None
        self.job_ids = []
        
        # Common skills keywords for extraction
        self.common_skills = {
            'python', 'java', 'javascript', 'sql', 'html', 'css', 'react', 'angular', 'vue',
            'node', 'django', 'flask', 'spring', 'aws', 'azure', 'gcp', 'docker', 'kubernetes',
            'git', 'agile', 'scrum', 'project management', 'data analysis', 'machine learning',
            'ai', 'deep learning', 'nlp', 'excel', 'powerpoint', 'word', 'communication',
            'leadership', 'teamwork', 'problem solving', 'critical thinking', 'customer service',
            'sales', 'marketing', 'accounting', 'finance', 'hr', 'recruiting', 'teaching',
            'research', 'writing', 'editing', 'design', 'photoshop', 'illustrator', 'figma'
        }
        
    def preprocess_text(self, text):
        """Clean and normalize text for better matching"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    def extract_skills(self, text):
        """Extract skills from text"""
        if not text:
            return set()
        
        text = self.preprocess_text(text)
        words = set(text.split())
        
        # Find common skills
        found_skills = set()
        for skill in self.common_skills:
            if skill in text:
                found_skills.add(skill)
        
        return found_skills
    
    def create_job_text(self, job):
        """Combine job fields into a single text for vectorization"""
        parts = []
        
        if job.title:
            parts.append(job.title * 3)  # Title is important - weight it 3x
        
        if job.description:
            parts.append(job.description)
        
        if job.requirements:
            parts.append(job.requirements)
        
        if job.category:
            parts.append(job.category)
        
        return ' '.join(parts)
    
    def create_candidate_text(self, user):
        """Combine candidate profile fields into a single text for vectorization"""
        parts = []
        
        if user.skills:
            # Skills are very important - weight them 3x
            parts.append(user.skills * 3)
        
        if user.qualifications:
            parts.append(user.qualifications)
        
        return ' '.join(parts)
    
    def fit_jobs(self, jobs):
        """Train the vectorizer on all active jobs"""
        if not jobs:
            return
        
        job_texts = []
        self.job_ids = []
        
        for job in jobs:
            text = self.preprocess_text(self.create_job_text(job))
            job_texts.append(text)
            self.job_ids.append(job.id)
        
        if job_texts:
            self.job_vectors = self.vectorizer.fit_transform(job_texts)
            self.is_fitted = True
    
    def get_match_scores(self, candidate_text, jobs=None):
        """
        Calculate match scores between a candidate and all jobs
        Returns list of (job_id, score) sorted by score descending
        """
        if not self.is_fitted or self.job_vectors is None:
            return []
        
        # Preprocess candidate text
        candidate_text = self.preprocess_text(candidate_text)
        
        if not candidate_text.strip():
            return [(job_id, 0.0) for job_id in self.job_ids]
        
        # Transform candidate text using the same vectorizer
        candidate_vector = self.vectorizer.transform([candidate_text])
        
        # Calculate cosine similarity
        similarities = cosine_similarity(candidate_vector, self.job_vectors)[0]
        
        # Create list of (job_id, score) pairs
        scores = [(self.job_ids[i], float(similarities[i])) 
                  for i in range(len(self.job_ids))]
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores
    
    def rank_candidates_for_job(self, job, candidates):
        """
        Rank multiple candidates for a single job
        Returns list of (candidate_id, score, skill_match_details) sorted by score descending
        """
        if not candidates:
            return []
        
        # Create job text and extract required skills
        job_text = self.preprocess_text(self.create_job_text(job))
        job_skills = self.extract_skills(job.requirements + ' ' + job.description)
        
        if not job_text.strip():
            return [(c.id, 0.0, {'matched_skills': [], 'missing_skills': list(job_skills)}) for c in candidates]
        
        # Create candidate texts
        candidate_texts = []
        candidate_ids = []
        
        for candidate in candidates:
            text = self.preprocess_text(self.create_candidate_text(candidate))
            candidate_texts.append(text)
            candidate_ids.append(candidate.id)
        
        # Fit vectorizer on job + candidates
        all_texts = [job_text] + candidate_texts
        vectors = self.vectorizer.fit_transform(all_texts)
        
        # Job is first vector
        job_vector = vectors[0]
        candidate_vectors = vectors[1:]
        
        # Calculate similarities
        similarities = cosine_similarity(job_vector, candidate_vectors)[0]
        
        # Create detailed results
        results = []
        for i, candidate in enumerate(candidates):
            candidate_skills = self.extract_skills(candidate.skills or '')
            matched_skills = list(candidate_skills & job_skills)
            missing_skills = list(job_skills - candidate_skills)
            
            # Calculate skill match percentage
            if job_skills:
                skill_match = len(matched_skills) / len(job_skills)
            else:
                skill_match = 0.5  # Default if no skills specified
            
            # Combined score (weighted average of text similarity and skill match)
            combined_score = (similarities[i] * 0.6) + (skill_match * 0.4)
            
            results.append({
                'candidate_id': candidate.id,
                'score': float(combined_score),
                'text_score': float(similarities[i]),
                'skill_score': float(skill_match),
                'matched_skills': matched_skills,
                'missing_skills': missing_skills,
                'total_required_skills': len(job_skills)
            })
        
        # Sort by combined score descending
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
    
    def get_skill_gap_analysis(self, user, job):
        """Analyze skill gaps between user and job"""
        job_skills = self.extract_skills(job.requirements + ' ' + job.description)
        user_skills = self.extract_skills(user.skills or '')
        
        matched = list(user_skills & job_skills)
        missing = list(job_skills - user_skills)
        extra = list(user_skills - job_skills)
        
        return {
            'matched_skills': matched,
            'missing_skills': missing,
            'extra_skills': extra,
            'match_percentage': len(matched) / len(job_skills) * 100 if job_skills else 0,
            'total_required': len(job_skills)
        }
    
    def get_blind_screening_score(self, candidate, job):
        """
        Calculate a blind screening score that ignores demographic information
        Focuses only on skills and qualifications
        """
        # Only use skills and qualifications text
        blind_text = self.preprocess_text(
            (candidate.skills or '') + ' ' + (candidate.qualifications or '')
        )
        
        job_text = self.preprocess_text(job.requirements or '')
        
        if not blind_text.strip() or not job_text.strip():
            return 0.0
        
        # Create temporary vectorizer for blind screening
        temp_vectorizer = TfidfVectorizer(stop_words='english')
        vectors = temp_vectorizer.fit_transform([job_text, blind_text])
        
        similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
        
        return float(similarity)
    
    def extract_keywords(self, text, top_n=10):
        """Extract important keywords from text using TF-IDF"""
        if not text or not text.strip():
            return []
        
        text = self.preprocess_text(text)
        
        # Create a temporary vectorizer for single document
        temp_vectorizer = TfidfVectorizer(
            stop_words='english',
            max_features=100,
            ngram_range=(1, 2)
        )
        
        try:
            temp_vectorizer.fit_transform([text])
            feature_names = temp_vectorizer.get_feature_names_out()
            return list(feature_names[:top_n])
        except:
            return []
    
    def suggest_skills(self, partial_text, limit=5):
        """Suggest skills based on partial input"""
        if not partial_text or len(partial_text) < 2:
            return []
        
        partial_text = partial_text.lower()
        suggestions = []
        
        for skill in self.common_skills:
            if skill.startswith(partial_text):
                suggestions.append(skill)
            elif partial_text in skill:
                suggestions.append(skill)
        
        # Remove duplicates and limit
        suggestions = list(dict.fromkeys(suggestions))
        return suggestions[:limit]


# Global matcher instance
matcher = JobMatcher()


def get_job_recommendations(user, jobs, top_n=5):
    """Get top N job recommendations for a user"""
    if not jobs:
        return []
    
    candidate_text = matcher.create_candidate_text(user)
    matcher.fit_jobs(jobs)
    scores = matcher.get_match_scores(candidate_text)
    
    # Filter out jobs with very low scores (below 5% match)
    min_score = 0.05
    filtered_scores = [(job_id, score) for job_id, score in scores if score >= min_score]
    
    return [job_id for job_id, _ in filtered_scores[:top_n]]


def get_top_candidates(job, candidates, top_n=10):
    """Get top N candidates for a job with detailed matching info"""
    if not candidates:
        return []
    
    results = matcher.rank_candidates_for_job(job, candidates)
    return results[:top_n]


def get_skill_recommendations(user_skills, all_jobs, top_n=5):
    """Recommend skills to learn based on job market demand"""
    all_required_skills = set()
    
    for job in all_jobs:
        skills = matcher.extract_skills(job.requirements + ' ' + job.description)
        all_required_skills.update(skills)
    
    user_skill_set = matcher.extract_skills(user_skills or '')
    
    # Skills in demand that user doesn't have
    recommended = list(all_required_skills - user_skill_set)
    
    # Count frequency of each skill across all jobs
    skill_freq = Counter()
    for job in all_jobs:
        skills = matcher.extract_skills(job.requirements + ' ' + job.description)
        skill_freq.update(skills)
    
    # Sort by frequency
    recommended.sort(key=lambda x: skill_freq.get(x, 0), reverse=True)
    
    return recommended[:top_n]