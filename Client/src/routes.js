/** 
  All of the routes for the Material Dashboard 2 React are added here,
  You can add a new route, customize the routes and delete the routes here.

  Once you add a new route on this file it will be visible automatically on
  the Sidenav.

  For adding a new route you can follow the existing routes in the routes array.
  1. The `type` key with the `collapse` value is used for a route.
  2. The `type` key with the `title` value is used for a title inside the Sidenav. 
  3. The `type` key with the `divider` value is used for a divider between Sidenav items.
  4. The `name` key is used for the name of the route on the Sidenav.
  5. The `key` key is used for the key of the route (It will help you with the key prop inside a loop).
  6. The `icon` key is used for the icon of the route on the Sidenav, you have to add a node.
  7. The `collapse` key is used for making a collapsible item on the Sidenav that contains other routes
  inside (nested routes), you need to pass the nested routes inside an array as a value for the `collapse` key.
  8. The `route` key is used to store the route location which is used for the react router.
  9. The `href` key is used to store the external links location.
  10. The `title` key is only for the item with the type of `title` and its used for the title text on the Sidenav.
  10. The `component` key is used to store the component of its route.
*/

import {Suspense, lazy} from "react";

// Material Dashboard 2 React components
import MDAvatar from "components/MDAvatar";

// @mui icons
import Icon from "@mui/material/Icon";

import { MdOutlineEventAvailable, MdFitbit, MdBuildCircle } from "react-icons/md";
import { FaBrain, FaFileWaveform, FaClipboardList } from "react-icons/fa6";
import { PiWavesBold } from "react-icons/pi";
import { FcSurvey } from "react-icons/fc";

// Images
import DashboardIcon from '@mui/icons-material/Dashboard';
import DescriptionIcon from '@mui/icons-material/Description';
import BoltIcon from '@mui/icons-material/Bolt';
import PollIcon from '@mui/icons-material/Poll';
import SensorsIcon from '@mui/icons-material/Sensors';
import AssessmentIcon from '@mui/icons-material/Assessment';
import TimelineIcon from '@mui/icons-material/Timeline';
import PersonIcon from '@mui/icons-material/Person';
import BiotechIcon from '@mui/icons-material/Biotech';
import { AccessAlarm, People, Article, IosShare } from "@mui/icons-material";


import { experimentalRoutes } from "views/Experimental/plugins";
import TimeSeriesAnalysis from "views/Reports/TimeSeriesAnalysis";

// BRAVO Platform Layouts
const DashboardOverview = lazy(() => import('views/Dashboard/Overview'));
const UploadDataView = lazy(() => import('views/Dashboard/UploadDataView'));
const ResearchAccessView = lazy(() => import('views/Dashboard/ShareResearchAccess'));
const ParticipantOverview = lazy(() => import('views/Dashboard/ParticipantOverview'));
const ImageVisualization = lazy(() => import('views/Experimental/ImageVisualization'));
const FormList = lazy(() => import('views/Survey/FormList'));
const FormEditor = lazy(() => import('views/Survey/Editor'));
const FormViewer = lazy(() => import('views/Survey/Viewer'));
const ParticipantSurveyRecords = lazy(() => import('views/Reports/ParticipantRecords'));
const FitbitAuth = lazy(() => import('views/Fitbit/Auth'));
const FitbitDashboard = lazy(() => import('views/Fitbit/Dashboard'));
const CustomizedAnalysis = lazy(() => import('views/CustomizedAnalysis'));

const TherapyHistory = lazy(() => import('views/Reports/TherapyHistory'));
const NeuralActivitySnapshot = lazy(() => import('views/Reports/NeuralActivitySnapshot'));
const ParticipantEvents = lazy(() => import('views/Reports/ParticipantEvents'));
const TherapeuticEffects = lazy(() => import('views/Reports/TherapeuticEffects'));
const ChronicNeuralActivity = lazy(() => import('views/Reports/ChronicNeuralActivity'));
const SessionOverview = lazy(() => import('views/Reports/SessionsOverview'));

const routes = {
  "Main": {
    children: [
      {
        type: "collapse",
        name: "Dashboard",
        key: "dashboard",
        component: <DashboardOverview />,
        route: "/dashboard",
        icon: <DashboardIcon/>,
        noCollapse: true,
      },
      {
        type: "collapse",
        name: "UploadRawData",
        key: "upload-data",
        component: <UploadDataView />,
        route: "/upload-data",
        icon: <IosShare/>,
        noCollapse: true,
      },
      { type: "divider", key: "divider-1" },
      {
        type: "collapse",
        name: "Survey and Questionnaire",
        key: "SurveyList",
        component: <FormList />,
        route: "/form-manager",
        icon: <FaClipboardList />,
        noCollapse: true,
      },
      {
        type: "collapse",
        name: "Forms Editor",
        key: "SurveyEditor",
        component: <FormEditor />,
        route: "/form-manager/:form_link",
        icon: <FaClipboardList />,
        noCollapse: true,
        hide: true,
      },
      {
        type: "collapse",
        name: "Forms Viewer",
        key: "SurveyViewer",
        component: <FormViewer />,
        route: "/survey/:form_link",
        icon: <FaClipboardList />,
        noCollapse: true,
        hide: true,
      },
      { type: "divider", key: "divider-2" },
      {
        type: "collapse",
        name: "ParticipantOverview",
        key: "participant-overview",
        component: <ParticipantOverview />,
        route: "/participant-overview/:participant_uid",
        icon: <PersonIcon/>,
        noCollapse: true,
      },
    ]
  },
  "GeneralReports": {
    icon: <AssessmentIcon />,
    name: "General Reports",
    children: [
      {
        key: "therapyHistory",
        name: "Therapy History",
        icon: <BoltIcon />,
        route: "/reports/therapy-history/:participant_uid",
        component: <TherapyHistory />,
      },
      {
        key: "nerualactivitysnapshot",
        name: "Neural Activity Snapshot",
        icon: <PiWavesBold />,
        route: "/reports/nerual-activity-snapshot/:participant_uid",
        component: <NeuralActivitySnapshot />,
      },
      {
        key: "therapeutic-effect",
        name: "Therapeutic Effect Analysis",
        icon: <FaFileWaveform />,
        route: "/reports/therapeutic-effect/:participant_uid",
        component: <TherapeuticEffects />,
      },
      {
        key: "chronic-neural-activity",
        name: "Chronic Neural Activity",
        icon: <TimelineIcon />,
        route: "/reports/chronic-neural-activity/:participant_uid",
        component: <ChronicNeuralActivity />,
      },
      {
        key: "events",
        name: "Chronic Events",
        icon: <MdOutlineEventAvailable />,
        route: "/reports/events/:participant_uid",
        component: <ParticipantEvents />,
      }
    ]
  },
  "SurveyReports": {
    icon: <FcSurvey />,
    name: "Surveys and Questionnaires",
    children: [
      {
        key: "FormRecords",
        name: "Form Records",
        icon: <FaClipboardList />,
        route: "/form-records/:participant_uid",
        component: <ParticipantSurveyRecords />,
      }
    ]
  },
  "FitbitReports": {
    icon: <MdFitbit />,
    name: "Fitbit Dashboard",
    children: [
      {
        key: "FitbitAuth",
        name: "Fitbit Request Authentication",
        icon: <MdFitbit />,
        route: "/fitbit/auth/:participant_uid",
        component: <FitbitAuth />,
      },
      {
        key: "FitbitDashboard",
        name: "Fitbit Dashboard",
        icon: <MdFitbit />,
        route: "/fitbit/dashboard/:participant_uid",
        component: <FitbitDashboard />,
      }
    ]
  },
  "ImagingReports": {
    icon: <FaBrain />,
    name: "Imaging Reports",
    children: [
      {
        key: "3dImageViewer",
        name: "3D Image Viewer",
        icon: <FaBrain />,
        route: "/reports/image-visualization/:participant_uid",
        component: <ImageVisualization />,
      }
    ]
  },
  "CustomizedAnalysis": {
    icon: <MdBuildCircle />,
    name: "Customized Analysis",
    children: [
      {
        key: "AnalysisBuilder",
        name: "Analysis Builder",
        icon: <MdBuildCircle />,
        route: "/analysis-builder/:participant_uid",
        component: <CustomizedAnalysis />,
      }
    ]
  },
}

/*
const routes = [
  
  { type: "title", name: "Reports for Percept™", key: "Percept-Reports-title", report_type: "PerceptReport"},
  {
    type: "collapse",
    name: "Reports",
    key: "percept-reports",
    icon: <DescriptionIcon/>,
    report_type: "PerceptReport",
    collapse: [
      {
        name: "TherapyHistory",
        key: "medtronic-therapy-history",
        icon: <BoltIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/percept/therapy-history",
        component: <TherapyHistory />,
      },
      {
        name: "BrainSenseSurvey",
        key: "survey",
        icon: <PollIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/percept/survey",
        component: <BrainSenseSurvey />,
      },
    ]
  },
  { type: "title", name: "General Reports", key: "Reports-title", report_type: "GeneralReport"},
  {
    type: "collapse",
    name: "Reports",
    key: "reports",
    icon: <DescriptionIcon/>,
    report_type: "GeneralReport",
    collapse: [
      {
        name: "TimeSeriesAnalysis",
        key: "time-series",
        icon: <SensorsIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/time-series",
        component: <TimeSeriesAnalysis />,
      },
    ]
  },
];
*/

/*
const routes = [
  {
    type: "collapse",
    name: "Dashboard",
    key: "dashboard",
    component: <DashboardOverview />,
    route: "/dashboard",
    icon: <DashboardIcon/>,
    noCollapse: true,
    identified: true,
    deidentified: true
  },
  {
    type: "collapse",
    name: "ShareResearchAccess",
    key: "access-permissions",
    component: <ResearchAccessView />,
    route: "/access-permissions",
    icon: <IosShare/>,
    noCollapse: true,
    identified: true,
    deidentified: true
  },
  {
    type: "collapse",
    name: "PatientLookupTable",
    key: "deidentification-table",
    component: <PatientLookupTable />,
    route: "/deidentification-table",
    icon: <People/>,
    noCollapse: true,
    identified: false,
    deidentified: true
  },
  { type: "divider", key: "divider-1" },
  {
    type: "collapse",
    name: "PatientOverview",
    key: "patient-overview",
    component: <PatientOverview />,
    route: "/patient-overview",
    icon: <PersonIcon/>,
    noCollapse: true,
    identified: true,
    deidentified: true
  },
  { type: "title", name: "Reports", key: "title-pages" },
  {
    type: "collapse",
    name: "Reports",
    key: "reports",
    identified: true,
    deidentified: true,
    icon: <DescriptionIcon/>,
    collapse: [
      {
        name: "TherapyHistory",
        key: "therapy-history",
        icon: <BoltIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/therapy-history",
        component: <TherapyHistory />,
        identified: true,
        deidentified: true
      },
      {
        name: "BrainSenseSurvey",
        key: "survey",
        icon: <PollIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/survey",
        component: <BrainSenseSurvey />,
        identified: true,
        deidentified: true
      },
      {
        name: "BrainSenseStreaming",
        key: "stream",
        icon: <SensorsIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/stream",
        component: <BrainSenseStreaming />,
        identified: true,
        deidentified: true
      },
      {
        name: "IndefiniteStreaming",
        key: "multistream",
        icon: <SensorsIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/multistream",
        component: <IndefiniteStreaming />,
        identified: true,
        deidentified: true
      },
      {
        name: "ChronicRecordings",
        key: "chronic-recordings",
        icon: <TimelineIcon style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/chronic-recordings",
        component: <ChronicBrainSense />,
        identified: true,
        deidentified: true
      },
      {
        name: "SessionOverview",
        key: "session-overview",
        icon: <Article style={{color: "white", margin: 0, padding: 0}}/>,
        route: "/reports/session-overview",
        component: <SessionOverview />,
        identified: true,
        deidentified: true
      },
    ]
  },
  {
    type: "collapse",
    name: "Experimental",
    key: "experimental",
    identified: true,
    deidentified: true,
    icon: <BiotechIcon/>,
    collapse: [
      ...experimentalRoutes
    ]
  },
  {
    type: "collapse",
    name: "Surveys",
    key: "surveys",
    component: <SurveyList />,
    route: "/surveys",
    icon: <DashboardIcon/>,
    noCollapse: true,
    identified: true,
    deidentified: true
  },
];
*/

export default routes;
