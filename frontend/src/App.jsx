import { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Spin } from 'antd';
import ProtectedRoute from './components/ProtectedRoute';
import CandidateLayout from './components/CandidateLayout';
import EmployerLayout from './components/EmployerLayout';
import { demoText, syncDemoModeFromLocation } from './utils/demoMode';

const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const LegalNotice = lazy(() => import('./pages/LegalNotice'));
const AccountSecurity = lazy(() => import('./pages/AccountSecurity'));
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
const CandidateMatchingHub = lazy(() => import('./pages/Employer/CandidateMatchingHub'));
const Applications = lazy(() => import('./pages/Employer/Applications'));
const ApplicationCenter = lazy(() => import('./pages/Employer/ApplicationCenter'));
const Screening = lazy(() => import('./pages/Employer/Screening'));
const BrowseJobs = lazy(() => import('./pages/Candidate/BrowseJobs'));
const Invitations = lazy(() => import('./pages/Candidate/Invitations'));
const Analytics = lazy(() => import('./pages/Candidate/Analytics'));
const AppliedJobs = lazy(() => import('./pages/Candidate/AppliedJobs'));
const AdminDataSources = lazy(() => import('./pages/Admin/DataSources'));
const CareerPassport = lazy(() => import('./pages/Candidate/CareerPassport'));
const EvidenceVault = lazy(() => import('./pages/Candidate/EvidenceVault'));
const Advisor = lazy(() => import('./pages/Candidate/Advisor'));
const PilotHub = lazy(() => import('./pages/Candidate/PilotHub'));

function RouteFallback() {
  return (
    <div
      style={{
        minHeight: '40vh',
        display: 'grid',
        placeItems: 'center',
      }}
    >
      <Spin size="large" description={demoText('页面加载中…', 'Loading…')} />
    </div>
  );
}

function App() {
  syncDemoModeFromLocation();
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/privacy" element={<LegalNotice kind="privacy" />} />
          <Route path="/terms" element={<LegalNotice kind="terms" />} />

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
            <Route path="career-passport" element={<CareerPassport />} />
            <Route path="evidence-vault" element={<EvidenceVault />} />
            <Route path="advisor" element={<Advisor />} />
            <Route path="pilot" element={<PilotHub />} />
            <Route path="help" element={<Help />} />
            <Route path="security" element={<AccountSecurity />} />
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
            <Route path="candidates" element={<CandidateMatchingHub />} />
            <Route path="applications/:jobId" element={<Applications />} />
            <Route path="applications" element={<ApplicationCenter />} />
            <Route path="screening" element={<Screening />} />
            <Route path="help" element={<Help />} />
            <Route path="security" element={<AccountSecurity />} />
          </Route>

          <Route
            path="/admin/data-sources"
            element={
              <ProtectedRoute role="admin">
                <AdminDataSources />
              </ProtectedRoute>
            }
          />

          <Route path="/" element={<Navigate to="/login" />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
