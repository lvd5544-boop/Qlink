import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import Help from './pages/Help';
import ProtectedRoute from './components/ProtectedRoute';
import CandidateLayout from './components/CandidateLayout';
import EmployerLayout from './components/EmployerLayout';
import CandidateDashboard from './pages/Candidate/Dashboard';
import UploadResume from './pages/Candidate/UploadResume';
import Interview from './pages/Candidate/Interview';
import JobList from './pages/Candidate/JobList';
import MyResumes from './pages/Candidate/MyResumes';
import EmployerDashboard from './pages/Employer/Dashboard';
import PostJob from './pages/Employer/PostJob';
import MyJobs from './pages/Employer/MyJobs';
import EditJob from './pages/Employer/EditJob';
import CandidateList from './pages/Employer/CandidateList';
import Applications from './pages/Employer/Applications';
import BrowseJobs from './pages/Candidate/BrowseJobs';
import Invitations from './pages/Candidate/Invitations';
import Analytics from './pages/Candidate/Analytics';
import AppliedJobs from './pages/Candidate/AppliedJobs';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        
        {/* 求职者路由 */}
        <Route
          path="/candidate"
          element={
            <ProtectedRoute role="candidate">
              <CandidateLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<CandidateDashboard />} />
	        <Route path="browse-jobs" element={<BrowseJobs />} />  
          <Route path="applied-jobs" element={<AppliedJobs />} />
          <Route path="upload-resume" element={<UploadResume />} />
          <Route path="interview" element={<Interview />} />
          <Route path="jobs" element={<JobList />} />
	        <Route path="my-resumes" element={<MyResumes />} />
          <Route path="invitations" element={<Invitations />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="help" element={<Help />} />
        </Route>

        {/* 招聘方路由 */}
        <Route
          path="/employer"
          element={
            <ProtectedRoute role="employer">
              <EmployerLayout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<EmployerDashboard />} />
          <Route path="post-job" element={<PostJob />} />
          <Route path="my-jobs" element={<MyJobs />} />
	  <Route path="edit-job/:jobId" element={<EditJob />} />
          <Route path="candidates/:jobId" element={<CandidateList />} />
          <Route path="applications/:jobId" element={<Applications />} />
          <Route path="help" element={<Help />} />
        </Route>

        <Route path="/" element={<Navigate to="/login" />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
