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
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Checkbox,
  IconButton,
  InputLabel,
  Input,
} from "@mui/material"

import { v4 as uuidv4 } from 'uuid';

import { createFilterOptions } from "@mui/material/Autocomplete";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDButton from "components/MDButton";
import MuiAlertDialog from "components/MuiAlertDialog";
import LoadingProgress from "components/LoadingProgress";
import TimelineItem from "components/Timeline/TimelineItem";

// core components
import RecordingSelect from "./RecordingSelect";
import RecordingEdit from "./RecordingEdit";
import ProcessingSelect from "./ProcessingSelect";
import ProcessingEdit from "./ProcessingEdit";
import RecordingAlignmentView from "./RecordingAlignmentView";

import { FaCirclePlay } from "react-icons/fa6";
import { MdAddBox, MdClose, MdEdit, MdOutlineMenu } from "react-icons/md";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary } from "assets/translation.js";
import ResultViewer from "./ResultViewers";

const filter = createFilterOptions();

function AnalysisBuilder({analysisId}) {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [analysisDrawerOpen, setAnalysisDrawerOpen] = useState(false);
  const [analysis, setAnalysis] = useState(false);
  const [data, setData] = useState(false);
  const [availableRecordings, setAvailableRecordings] = useState([]);
  const [availableProcessingNodes, setAvailableProcessingNodes] = useState([]);
  const [configureRecording, setConfigureRecording] = useState({ configuration: {}, show: false });
  const [editChannelName, setEditChannelName] = useState({ show: false, name: "", id: "" });

  const [showRecordingList, setShowRecordingList] = useState({current: [], show: false});
  const [showProcessingList, setShowProcessingList] = useState({id: "", current: null, show: false});

  const [editRecording, setEditRecording] = useState({show: false});
  const [editProcessing, setEditProcessing] = useState({show: false});
  const [editAlignment, setEditAlignment] = useState({show: false});
  const [resultDialog, setResultDialog] = useState({show: false});

  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
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
      console.log(response.data)
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
      <MDBox display={"flex"} flexDirection={"row"} alignItems={"center"}>
        <MDTypography variant={"h5"} fontWeight={"bold"} fontSize={24}>
          {analysis.Name}
        </MDTypography>
        <IconButton onClick={() => setAnalysisDrawerOpen((a) => !a)}>
          <MdOutlineMenu />
        </IconButton>
      </MDBox>
      
      <Drawer open={analysisDrawerOpen} onClose={() => setAnalysisDrawerOpen(false)} style={{position: "relative"}}>
        <MDBox>
          <MDBox px={3} pt={2}>
            <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={18}>
              {"Add Source Data"}
            </MDTypography>
          </MDBox>
          <List>
            <ListItem disablePadding>
              <ListItemButton onClick={() => setShowRecordingList({name: "", current: [], show: true})}>
                <ListItemIcon style={{minWidth: 36}}>
                  <MdAddBox color={"#FF0000"} />
                </ListItemIcon>
                <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={15}>
                  {"Add Recordings"}
                </MDTypography>
              </ListItemButton>
            </ListItem>
            <ListItem disablePadding>
              <ListItemButton>
                <ListItemIcon style={{minWidth: 36}}>
                  <MdAddBox color={"#FF0000"} />
                </ListItemIcon>
                <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={15}>
                  {"Add Questionnaire Scores"}
                </MDTypography>
              </ListItemButton>
            </ListItem>
            <ListItem disablePadding>
              <ListItemButton onClick={() => {
                let connectedNodes = [];
                for (let i in nodes) {
                  for (let j in nodes[i]) {
                    if (nodes[i][j].type == "RecordingNode") {
                      connectedNodes.push(nodes[i][j]);
                    }
                  }
                }
                setEditAlignment({nodes: connectedNodes, show: true})
              }}>
                <ListItemIcon style={{minWidth: 36}}>
                  <MdAddBox color={"#FF0000"} />
                </ListItemIcon>
                <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={15}>
                  {"Edit Recording Alignments"}
                </MDTypography>
              </ListItemButton>
            </ListItem>
          </List>
          
          <MDBox px={3} pt={2}>
            <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={18}>
              {"Processing Pipeline"}
            </MDTypography>
          </MDBox>
          <List>
            <ListItem disablePadding>
              <ListItemButton>
                <ListItemIcon style={{minWidth: 36}}>
                  <MdAddBox color={"#FF0000"} />
                </ListItemIcon>
                <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={15}>
                  {"Use Processing Template"}
                </MDTypography>
              </ListItemButton>
            </ListItem>
            <ListItem disablePadding>
              <ListItemButton onClick={() => setShowProcessingList(true)}>
                <ListItemIcon style={{minWidth: 36}}>
                  <MdAddBox color={"#FF0000"} />
                </ListItemIcon>
                <MDTypography variant={"h6"} fontWeight={"bold"} fontSize={15}>
                  {"Add Processing Node"}
                </MDTypography>
              </ListItemButton>
            </ListItem>
          </List>
        </MDBox>
      </Drawer>

      <MDBox pt={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} sx={{display: "flex", justifyContent: "space-between"}}>
            <MDBox>
              <MDButton color={"info"} onClick={() => saveProcessingPipeline(false)} style={{marginLeft: 5}}>
                {"Save Analysis Pipeline"}
              </MDButton>
              <MDButton color={"success"} onClick={() => saveProcessingPipeline(true)} style={{marginLeft: 10}}>
                <FaCirclePlay size={15} style={{marginRight: 5}}/> {"Run Processing"}
              </MDButton>
            </MDBox>
          </Grid>
          <Grid item xs={12} sx={{display: "flex", flexDirection: "row", overflowX: "auto"}}>
            {nodes.map((nodeGroup, nodeIndex) => {
              console.log(nodeGroup)
              return (
                <Card key={nodeGroup[0].id} style={{width: 300, minHeight: 600, marginRight: 15, marginTop: 5, marginBottom: 5}}>
                  <MDBox
                    bgColor={"white"}
                    variant="gradient"
                    borderRadius="sm"
                    sx={{ background: ({ palette: { background } }) => background.card }}
                  >
                    <MDBox pt={3} px={3} display={"flex"} flexDirection={"row"} alignItems={"center"}>
                      <MDTypography variant="h6" fontWeight="medium" color={"dark"}>
                        {nodeGroup[0].name}
                      </MDTypography>
                      <IconButton color="info" onClick={() => {
                        setShowRecordingList({name: nodeGroup[0].name, id: nodeGroup[0].id, current: nodeGroup[0].data.map((a) => a.Id), show: true})
                      }}>
                        <MdEdit />
                      </IconButton>
                      <IconButton color="error" onClick={() => {
                        setNodes((nodes) => {
                          nodes.splice(nodeIndex, 1);
                          return [...nodes];
                        });
                      }}>
                        <MdClose />
                      </IconButton>
                    </MDBox>
                    <MDBox p={2}>
                      <TimelineItem color={"info"} title={"Step 1"} description={nodeGroup[0].data[0].Type}
                        onClick={() => {
                          if (nodeGroup[0].data[0].Type != "Processed Output") {
                            setEditRecording({show: true, node: nodeGroup[0]});
                          }
                        }} />
                      {nodeGroup.map((a,i) => {
                        if (i > 0) {
                          return <TimelineItem key={a.id} color={"info"} title={a.data.Type} description={a.data.Description} result={a.result} onViewResult={() => {
                            setResultDialog({show: true, node: a});
                          }} onClick={() => setEditProcessing({node: a, show: true})} />
                        }
                      })}
                      <TimelineItem color={"info"} icon={<MdAddBox />} title={"Add Processing Step"} onClick={() => setShowProcessingList({id: nodeGroup[0].id, show: true})} lastItem />
                    </MDBox>
                  </MDBox>
                </Card>
              );
            })}
          </Grid>
        </Grid>
      </MDBox>
      
      <Dialog open={showRecordingList.show} onClose={() => setShowRecordingList({current: [], show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <RecordingSelect recordings={availableRecordings} existingGroups={nodes.map((a) => a[0])} name={showRecordingList.name} currentSelect={showRecordingList.current} onSelectRecording={(recordings, name) => {
          const selectedRecording = availableRecordings.filter((a) => recordings.includes(a.Id));
          selectedRecording.push(...nodes.map((a) => ({
            Id: a[0].id,
            Name: a[0].name,
            Type: "Processed Output"
          })).filter((a) => recordings.includes(a.Id)));
          if (!showRecordingList.id) {
            const newNode = {
              id: uuidv4(),
              name: name,
              type: "RecordingNode",
              data: selectedRecording,
            };
            setNodes((nodes) => {
              nodes.push([newNode]);
              return [...nodes];
            });
          } else {
            setNodes((nodes) => {
              for (let i in nodes) {
                if (nodes[i][0].id == showRecordingList.id) {
                  nodes[i][0].data = selectedRecording;
                  nodes[i][0].name = name;
                }
              }
              return [...nodes];
            });
          }
          setShowRecordingList({current: [], show: false});
        }} onClose={() => setShowRecordingList({current: [], show: false})} />
      </Dialog>

      <Dialog open={editRecording.show} onClose={() => setEditRecording({...editRecording, show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <RecordingEdit editNode={editRecording.node} onSetRecordingNode={(node) => {
          setNodes((nodes) => {
            for (let i in nodes) {
              if (nodes[i][0].id == showRecordingList.id) {
                nodes[i][0] = node;
              }
            }
            return [...nodes];
          });
          setEditRecording({...editRecording, show: false});
        }} onClose={() => setEditRecording({...editRecording, show: false})} />
      </Dialog>

      <Dialog open={showProcessingList.show} onClose={() => setShowProcessingList({id: "", show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <ProcessingSelect processingNodes={availableProcessingNodes} onSetProcessingNode={(node) => {
          setNodes((nodes) => {
            for (let i in nodes) {
              if (nodes[i][0].id == showProcessingList.id) {
                nodes[i].push(...node.map((a) => ({
                  id: a.Id,
                  type: a.NodeType,
                  data: a,
                  position: {x: 0, y: 0}
                })));
              }
            }
            return [...nodes];
          });
          setShowProcessingList({id: "", show: false});
        }} onClose={() => setShowProcessingList({id: "", show: false})} />
      </Dialog>

      <Dialog open={editProcessing.show} onClose={() => setEditProcessing({...editProcessing, show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <ProcessingEdit editNode={editProcessing.node} onSetProcessingNode={(node) => {
          setNodes((nodes) => {
            for (let i in nodes) {
              for (let j in nodes[i]) {
                if (nodes[i][j].id == editProcessing.node.id) {
                  if (!node) {
                    nodes[i].splice(j, 1);
                  } else {
                    nodes[i][j] = node;
                  }
                }
              }
            }
            return [...nodes];
          });
          setEditProcessing({...editProcessing, show: false});
        }} onClose={() => setEditProcessing({...editProcessing, show: false})} />
      </Dialog>

      <Dialog open={editAlignment.show} onClose={() => setEditAlignment({...editAlignment, show: false})} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
      >
        <RecordingAlignmentView nodes={editAlignment.nodes} />
      </Dialog>

      <Dialog open={resultDialog.show} onClose={() => {}} 
        PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 1000 }} }}
      >
        <ResultViewer analysisId={analysisId} participant_uid={participant_uid} node={resultDialog.node} onClose={() => setResultDialog({...resultDialog, show: false})} />
      </Dialog>

    </Card>
  ) : null;
}

export default AnalysisBuilder;
