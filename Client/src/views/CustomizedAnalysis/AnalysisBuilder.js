/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Autocomplete,
  Dialog,
  DialogContent,
  TextField,
  Card,
  Drawer,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon,
  Grid,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Checkbox,
  IconButton,
  InputLabel,
  Input,
} from "@mui/material"

import { 
  ReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  applyNodeChanges,
  Controls,
  MiniMap,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './FlowchartNodes/flowchart.css';

import RecordingNode from "./FlowchartNodes/RecordingNode";
import RecordingGroupNode from "./FlowchartNodes/RecordingGroupNode";
import SingleInputProcessingNode from "./FlowchartNodes/SingleInputProcessingNode"

import { v4 as uuidv4 } from 'uuid';

import { createFilterOptions } from "@mui/material/Autocomplete";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";
import LoadingProgress from "components/LoadingProgress";
import SettingsIcon from "@mui/icons-material/Settings";

// core components
import DatabaseLayout from "layouts/DatabaseLayout";
import RecordingSelect from "./RecordingSelect";
import RecordingEdit from "./RecordingEdit";
import ProcessingSelect from "./ProcessingSelect";
import ProcessingEdit from "./ProcessingEdit";

import { FaCirclePlay } from "react-icons/fa6";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";

const filter = createFilterOptions();
const flowchartNodeTypes = {
  RecordingNode: RecordingNode, 
  RecordingGroupNode: RecordingGroupNode, 
  SingleInputProcessingNode: SingleInputProcessingNode,
};


function AnalysisBuilder({analysisId}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [analysis, setAnalysis] = useState(false);
  const [data, setData] = useState(false);
  const [availableRecordings, setAvailableRecordings] = useState([]);
  const [availableProcessingNodes, setAvailableProcessingNodes] = useState([]);
  const [configureRecording, setConfigureRecording] = useState({ configuration: {}, show: false });
  const [editChannelName, setEditChannelName] = useState({ show: false, name: "", id: "" });

  const [showRecordingList, setShowRecordingList] = useState(false);
  const [showProcessingList, setShowProcessingList] = useState(false);

  const [editRecording, setEditRecording] = useState({show: false});
  const [editProcessing, setEditProcessing] = useState({show: false});

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const onConnect = useCallback((params) => {
    setEdges((eds) => addEdge(params, eds));
  }, [setEdges]);

  const [alert, setAlert] = useState(null);

  useEffect(() => {
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "ProcessingNodes",
      ParticipantId: participant_uid,
    }).then((response) => {
      setAvailableProcessingNodes(response.data);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, []);

  useEffect(() => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "AnalysisOverview",
      ParticipantId: participant_uid,
      AnalysisId: analysisId
    }).then((response) => {
      setAnalysis(response.data.Analysis);
      setAvailableRecordings(response.data.Recordings);
      if (response.data.Configurations.Edges) {
        setEdges([...response.data.Configurations.Edges]);
      } else {
        setEdges([]);
      }
      if (response.data.Configurations.Nodes) {
        setNodes([...response.data.Configurations.Nodes]);
      } else {
        setNodes([])
      }
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [analysisId]);

  useEffect(() => {
    
  }, [nodes, edges])

  const saveProcessingPipeline = (startProcess) => {
    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryCustomizedAnalysis", {
      RequestType: "SaveAnalysisPipeline",
      ParticipantId: participant_uid,
      AnalysisId: analysisId,
      Nodes: nodes,
      Edges: edges,
      StartProcessing: startProcess
    }).then((response) => {
      setAnalysis(response.data.Analysis);
      setAvailableRecordings(response.data.Recordings);
      if (response.data.Configurations.Edges) {
        setEdges([...response.data.Configurations.Edges]);
      } else {
        setEdges([]);
      }
      if (response.data.Configurations.Nodes) {
        setNodes([...response.data.Configurations.Nodes]);
      } else {
        setNodes([])
      }
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  };

  const handleStreamConfiguration = (plotlyPoint) => {
    
  }

  const handleDeleteVerification = () => {
    
  };

  const handleUpdateConfiguration = () => {
    
  };

  const renderChannelLists = ({index, style}) => {
    
  };

  return analysis ? (
    <Card width={"100%"} style={{paddingTop: 15, paddingBottom: 15, paddingLeft: 15, paddingRight: 15}}>
      {alert}
      <MDBox>
        <MDTypography variant={"h5"} fontWeight={"bold"} fontSize={24}>
          {analysis.Name}
        </MDTypography>
      </MDBox>
      <MDBox pt={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} sx={{display: "flex", justifyContent: "space-between"}}>
            <MDBox>
              <MDButton color={"error"} onClick={() => setShowRecordingList(true)}>
                {"Add Recording for Analysis"}
              </MDButton>
              <MDButton color={"info"} onClick={() => setShowProcessingList(true)} style={{marginLeft: 10}}>
                {"Add Processing Node"}
              </MDButton>
              <MDButton color={"info"} onClick={() => {}} style={{marginLeft: 10}}>
                {"Use Processing Template"}
              </MDButton>
            </MDBox>
            <MDBox>
              <MDButton color={"success"} onClick={() => saveProcessingPipeline(false)}>
                {"Save Analysis Pipeline"}
              </MDButton>
            </MDBox>
          </Grid>
          <Grid item xs={12} sx={{minHeight: 600}}>
            <ReactFlow
              nodeTypes={flowchartNodeTypes} nodes={nodes} edges={edges}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
              onNodeClick={(event, node) => {
                if (node.type == "RecordingNode") {
                  setEditRecording({show: true, node: node});
                } else if (node.type == "RecordingGroupNode") {
                  
                } else {
                  setEditProcessing({show: true, node: node});
                }
                console.log(node)
              }}
            >
              <Controls />
              <MiniMap />
            </ReactFlow>
          </Grid>
          <Grid item xs={12} sx={{display: "flex", justifyContent: "space-between"}}>
            <MDBox>
              <MDButton color={"success"} onClick={() => saveProcessingPipeline(true)}>
                <FaCirclePlay size={15} style={{marginRight: 5}}/>
                {"Run Processing"}
              </MDButton>
            </MDBox>
          </Grid>
        </Grid>
      </MDBox>
      
      <Dialog open={showRecordingList} onClose={() => setShowRecordingList(false)} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <RecordingSelect recordings={availableRecordings} onSelectRecording={(recordings) => {
          
          const groupNode = {
            id: uuidv4(),
            type: "RecordingGroupNode",
            data: {
              Name: "Recording Group",
              List: recordings
            },
            position: {x: 0, y: 0}
          };

          let newNodes = [];
          const selectedRecording = availableRecordings.filter((a) => recordings.includes(a.Id));
          for (let i in selectedRecording) {
            newNodes.push({
              id: uuidv4(),
              type: "RecordingNode",
              data: selectedRecording[i],
              position: {x: 0, y: 0}
            });
          }
          newNodes.push(groupNode);

          setNodes((nds) => nds.concat(newNodes));
          setEdges((eds) => {
            for (let i in newNodes) {
              if (groupNode.id != newNodes[i].id) {
                eds = addEdge({
                  id: newNodes[i].id + "-" + groupNode.id,
                  source: newNodes[i].id, 
                  target: groupNode.id,
                }, eds);
              }
            }
            return eds;
          });
          
          setShowRecordingList(false);
        }} onClose={() => setShowRecordingList(false)} />
      </Dialog>

      <Dialog open={editRecording.show} onClose={() => setEditRecording({...editRecording, show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <RecordingEdit editNode={editRecording.node} onSetRecordingNode={(node) => {
          setNodes((nds) => {
            return nds;
          });
          setEditRecording({...editRecording, show: false});
        }} onClose={() => setEditRecording({...editRecording, show: false})} />
      </Dialog>

      <Dialog open={showProcessingList} onClose={() => setShowProcessingList(false)} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <ProcessingSelect processingNodes={availableProcessingNodes} onSetProcessingNode={(node) => {
          setNodes((nds) => {
            return nds.concat([{
              id: node.Id,
              type: node.NodeType,
              data: node,
              position: {x: 0, y: 0}
            }]);
          });
          setShowProcessingList(false);
        }} onClose={() => setShowProcessingList(false)} />
      </Dialog>

      <Dialog open={editProcessing.show} onClose={() => setEditProcessing({...editProcessing, show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <ProcessingEdit editNode={editProcessing.node} onSetProcessingNode={(node) => {
          setNodes((nds) => {
            return nds;
          });
          setEditProcessing({...editProcessing, show: false});
        }} onClose={() => setEditProcessing({...editProcessing, show: false})} />
      </Dialog>

      <Dialog open={configureRecording.show} onClose={() => setConfigureRecording({...configureRecording, show: false})}>
        <MDBox px={2} pt={2}>
          <MDTypography variant="h5">
            {"Configure Recording for Analysis"}
          </MDTypography>
          <MDTypography variant="p" fontSize={15}>
            {configureRecording.title || ""}
          </MDTypography>
        </MDBox>
        <DialogContent style={{minWidth: 500}} >
        </DialogContent>
        <MDBox px={2} py={2} style={{display: "flex", justifyContent: "space-between"}}>
          <MDBox px={2} py={2} style={{display: "flex", justifyContent: "space-between"}}>
            <MDButton variant={"gradient"} color={"error"} onClick={handleDeleteVerification}>
              {"Delete"}
            </MDButton>
          </MDBox>
          <MDBox px={2} py={2} style={{display: "flex", justifyContent: "space-around"}}>
            <MDButton variant={"gradient"} color={"secondary"} onClick={() => setConfigureRecording({...configureRecording, show: false})}>
              {"Cancel"}
            </MDButton>
            <MDButton variant={"gradient"} color={"success"} onClick={handleUpdateConfiguration}>
              {"Update"}
            </MDButton>
          </MDBox>
        </MDBox>
      </Dialog>
    </Card>
  ) : null;
}

export default AnalysisBuilder;
