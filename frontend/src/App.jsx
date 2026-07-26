import { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import ProtectedRoute from './components/ProtectedRoute';
import CandidateLayout from './components/CandidateLayout';
import EmployerLayout from './components/EmployerLayout';

const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Help = lazy(() => import('./pages/Help'));
const CandidateDashboard = lazy(() => import('./pages/Candidate/Dashboard'));
const UploadResume = lazy(() => import('./pages/Candidate/UploadResume'));
const Interview = lazy(() => import('./pages/Candidate/Interview'));
const JobList = lazy(() => import('./pages/Candidate/JobList'));
const MyResumes = lazy(() => import('./pages/Candidate/MyResumes'));
const EmployerDashboard = lazy(() => import('./pages/Employer/Dashboard'));
const PostJob = lazy(() => import('./pages/Employer/PostJob'));
const MyJobs = lazy(() => import('./pages/Employer/MyJobs'));
const EditJob = lazy(() => import('./pages/Employer/EditJob'));
const CandidateList = lazy(() => import('./pages/Employer/CandidateList'));
const Applications = lazy(() => import('./pages/Employer/Applications'));
const BrowseJobs = lazy(() => import('./pages/Candidate/BrowseJobs'));
const Invitations = lazy(() => import('./pages/Candidate/Invitations'));
const Analytics = lazy(() => import('./pages/Candidate/Analytics'));
const AppliedJobs = lazy(() => import('./pages/Candidate/AppliedJobs'));

function RouteFallback() {
  return (
    <div
      style={{
        minHeight: '40vh',
        display: 'grid',
        placeItems: 'center',
      }}
    >
      <Spin size="large" tip="页面加载中…" />
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

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
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
