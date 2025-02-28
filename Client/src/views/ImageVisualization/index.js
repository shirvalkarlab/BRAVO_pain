/**
=========================================================
* UF BRAVO Platform
=========================================================

* Copyright 2025 by Jackson Cagle, Fixel Institute
* The source code is made available under a Creative Common NonCommercial ShareAlike License (CC BY-NC-SA 4.0) (https://creativecommons.org/licenses/by-nc-sa/4.0/) 

 =========================================================

* The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
*/

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  TextField,
  Autocomplete,
  Dialog,
  DialogContent,
  Popover,
  Card,
  Grid,
  Modal,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  IconButton,
} from "@mui/material";

import { ViewInAr, Timeline } from "@mui/icons-material";
import { TwitterPicker, BlockPicker } from "react-color";

import React from "react";
import * as THREE from "three";
import { Canvas, useThree } from '@react-three/fiber';
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader";

import colormap from "colormap";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import RadioButtonGroup from "components/RadioButtonGroup";
import MDBadge from "components/MDBadge";
import MDButton from "components/MDButton";
import FormField from "components/MDInput/FormField";
import LoadingProgress from "components/LoadingProgress";

import ImagingSelect from "./ImagingSelect";

// core components
import {
  CameraController,
  CoordinateSystem,
  ShadowLight,
  Model,
  Tractography,
  VolumetricObject,
  SphereObject,
  retrieveModels,
  computeElectrodePlacement
} from "graphing-utility/Volumetric";

import DatabaseLayout from "layouts/DatabaseLayout";

import { SessionController } from "database/session-control";
import { usePlatformContext, setContextState } from "context.js";
import { dictionary, dictionaryLookup } from "assets/translation.js";
import { FaEye, FaPen } from "react-icons/fa6";

function ImageVisualization() {
  const navigate = useNavigate();
  const [controller, dispatch] = usePlatformContext();
  const { language } = controller;
  const { participant_uid } = useParams();

  const [existingFiles, setExistingFiles] = useState(false);
  const [showRecordingList, setShowRecordingList] = useState(false);
  const [availableItems, setAvailableItems] = React.useState([]);
  const [controlItems, setControlItems] = React.useState([]);
  const [descriptor, setDescriptor] = React.useState({});

  const [addItemModal, setAddItemModal] = useState({show: false});
  const [popup, setPopupState] = React.useState({item: ""});
  const [editTargetEntry, setEditTargetEntry] = React.useState({show: false, item: "", name: "", targetPoint: [0,0,0], entryPoint: [10,10,10]});

  const [cameraLock, setCameraLock] = React.useState(false);
  const [worldMatrix, setWorldMatrx] = React.useState(null);
  
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    const matrix = new THREE.Matrix4();
    matrix.set(1, 0, 0, 0,
               0, 0, 1, 0,
               0, -1, 0, 0,
               0, 0, 0, 1);
    setWorldMatrx(matrix);
  }, []);

  useEffect(() => {
    if (!participant_uid) {
      navigate("/dashboard", {replace: false});
      return;
    }
    setContextState(dispatch, "report", "CustomizedAnalysis");

    setAlert(<LoadingProgress/>);
    SessionController.query("/api/queryImageSourceFiles", {
      RequestType: "ListAll",
      ParticipantId: participant_uid
    }).then((response) => {
      setAvailableItems(response.data)
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
  }, [participant_uid]);

  useEffect(() => {
    
  }, [availableItems, descriptor]);

  const downloadModelsFromDescriptor = async () => {
    setAlert(<LoadingProgress/>);
    let allItems = [];
    const files = Object.keys(descriptor);
    for (let item of availableItems) {
      if (files.includes(item.file)) {
        if (!item.downloaded) {
          const data = await retrieveModels(participant_uid, item, descriptor[item.file].color);
          if (item.type === "electrode") {
            if (descriptor[item.file].targetPoint) data[0].targetPts = descriptor[item.file].targetPoint;
            if (descriptor[item.file].entryPoint) data[0].entryPts = descriptor[item.file].entryPoint;
          } else if (item.type === "sphere") {
            data[0].targetPts = descriptor[item.file].targetPoints;
          } else {
            const index = checkItemIndex(item);    
            availableItems[index].downloaded = true;
          }
          allItems = [...allItems, ...data];
        }
      }
    }
    setControlItems(allItems);
    setAvailableItems(availableItems);
    setAlert(null);
  }

  const checkItemIndex = (item) => {
    for (var i in availableItems) {
      if (availableItems[i].Id == item.Id) return i; 
    }
  };

  const addModel = async (item, color) => {
    for (let i in controlItems) {
      if (controlItems[i].id == item.Id) {
        controlItems[i].show = !controlItems[i].show;
        return setControlItems([...controlItems]);
      }
    }
  };

  const addModels = async (items, colors) => {
    const allItems = [];
    for (let i in items) {
      const item = items[i];
      if (!item.Downloaded) {
        const data = await retrieveModels(participant_uid, item, item.Color);
        if (item.DataType == "Blender Scene") {
          const loader = new GLTFLoader();
          loader.load(data[0].data, (gltf) => {
            const newItems = gltf.scene.children.map((mesh) => {
              return { id: mesh.name, filename: mesh.name, type: "GLB", downloaded: true, data: mesh, show: true, isMesh: mesh.isMesh };
            })
            setControlItems((controlItems) => [...controlItems, ...newItems]);
            setAvailableItems((availableItems) => [...availableItems, ...newItems.map((a) => ({...a, Id: a.id, Name: a.id, DataType: a.type}))]);
            setAlert(null);
          }, (xhr) => {
            setAlert(<LoadingProgress message={"Loaded " + (xhr.loaded/1000000).toFixed(2) + " MB"}/>);
          }, (error) => {
            console.log(error);
          })
        } else if (item.Id.startsWith("TemplateElectrode_")) {
          item.Downloaded = true
          availableItems.push({...item, 
            Id: data[0].id,
            DataType: "Electrodes"
          });
          allItems.push(...data);
        } else {
          const index = checkItemIndex(item);
          availableItems[index].Downloaded = true;
          allItems.push(...data);
        }
      } else {
        for (let k in controlItems) {
          if (controlItems[k].Id == item.Id) {
            controlItems[k].Show = !controlItems[k].Show;
          }
        }
      }
    }
    setAvailableItems(availableItems);
    setControlItems([...controlItems, ...allItems]);
    setShowRecordingList(false);
  };

  const updateObjectColor = (item, color) => {
    for (let i in controlItems) {
      if (controlItems[i].id == item.Id) {
        controlItems[i].color = color.hex;
        SessionController.query("/api/queryImageSourceFiles", {
          RequestType: "UpdateModel",
          ParticipantId: participant_uid,
          SourceId: item.Id,
          Metadata: {
            Color: color.hex
          }
        });
        return setControlItems([...controlItems]);
      }
    }
  };

  const updateTargetPoints = () => {
    setAlert(<LoadingProgress/>);
    setControlItems((controlItems) => {
      for (let i in controlItems) {
        if (controlItems[i].id == editTargetEntry.item) {
          controlItems[i].filename = editTargetEntry.name;
          controlItems[i].targetPt = editTargetEntry.targetPoint.map((value) => parseFloat(value));
          controlItems[i].entryPt = editTargetEntry.entryPoint.map((value) => parseFloat(value));
        }
      }
      return [...controlItems];
    });
    SessionController.query("/api/queryImageSourceFiles", {
      RequestType: "UpdateModel",
      ParticipantId: participant_uid,
      SourceId: editTargetEntry.item,
      Metadata: {
        Name: editTargetEntry.name,
        EntryPoint: editTargetEntry.entryPoint.map((value) => parseFloat(value)),
        TargetPoint: editTargetEntry.targetPoint.map((value) => parseFloat(value))
      }
    }).then((response) => {
      setAvailableItems((availableItems) => {
        for (let i in availableItems) {
          if (availableItems[i].Id == editTargetEntry.item) {
            availableItems[i].Name = editTargetEntry.name;
          }
        }
        return [...availableItems];
      });
      setAlert(null);
    }).catch((error) => {
      SessionController.displayError(error, setAlert);
    });
    setEditTargetEntry({...editTargetEntry, show: false});
  };

  const lockCamera = () => {
    setCameraLock((cameraLock) => {
      return !cameraLock;
    });
  }

  return (
    <>
      {alert}
      <DatabaseLayout>
        <MDBox pt={3}>
          <MDBox>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Card sx={{width: "100%"}}>
                  <Grid container>
                    <Grid item xs={12}>
                      <MDBox display={"flex"} justifyContent={"space-between"} p={2}>
                        <MDTypography variant={"h6"} fontSize={24}>
                          {dictionary.ImageVisualization.Title[language]}
                        </MDTypography>
                        <MDBox display={"flex"} flexDirection={"column"}>
                          <MDButton size="medium" variant="contained" color="info" onClick={() => setShowRecordingList(true)}>
                            {dictionaryLookup(dictionary.ImageVisualization, "AddItem", language)}
                          </MDButton>
                        </MDBox>
                      </MDBox>
                    </Grid>
                    <Grid item xs={12}>
                      <Grid container>
                        {availableItems.map((item) => {
                          let downloadedItem = null;
                          for (let i in controlItems) {
                            if (controlItems[i].id == item.Id) {
                              downloadedItem = controlItems[i]
                            }
                          }

                          return <Grid item xs={12} sm={6} md={4}>
                            <MDBox px={2} style={{display: "flex", flexDirection: "row", alignItems: "center"}}>
                              {downloadedItem ? (
                                <>
                                  <IconButton
                                    style={{padding: 0, marginRight: 3, borderStyle: "solid", borderColor: "#000000", borderWidth: 1, height: "100%"}} 
                                    onClick={(event) => setPopupState({item: item.Id, anchorEl: event.currentTarget})}
                                  >
                                    <img style={{background: downloadedItem.color, padding: 8, borderRadius: "50%"}}/>
                                  </IconButton>
                                  <Popover 
                                    open={popup.item == item.Id}
                                    onClose={() => setPopupState({item: "", anchorEl: null})}
                                    anchorEl={popup.anchorEl}
                                    anchorOrigin={{
                                      vertical: 'bottom',
                                      horizontal: 'left',
                                    }}
                                    transformOrigin={{
                                      vertical: "top",
                                      horizontal: 'left',
                                    }}
                                    PaperProps={{sx: {boxShadow: "none"}}}
                                  >
                                    <TwitterPicker color={downloadedItem.color} onChange={(color) => updateObjectColor(item, color)}/>
                                  </Popover>
                                </>
                              ) : null}
                              <MDTypography variant="h6" fontSize={15} color={downloadedItem ? "dark" : "light"} style={{cursor: "pointer"}} onClick={() => addModel(item)}>
                                {item.Name}
                              </MDTypography>
                              {downloadedItem ? (<IconButton variant="contained" color={downloadedItem.show ? "info" : "light"} onClick={() => addModel(item)}>
                                <FaEye fontSize={10} />
                              </IconButton>) : null}
                              {downloadedItem && item.DataType === "Electrodes" ? (<IconButton variant="contained" color={"info"} onClick={() => setEditTargetEntry({item: item.Id, name: item.Name, targetPoint: downloadedItem.targetPt, entryPoint: downloadedItem.entryPt, show: true})}>
                                <FaPen fontSize={10} />
                              </IconButton>) : null}
                              {downloadedItem && item.type === "volume" ? (<IconButton variant="contained" color={cameraLock ? "light" : "info"} onClick={lockCamera}>
                                <FaPen fontSize={10} />
                              </IconButton>) : null}
                            </MDBox>
                          </Grid>
                        })}
                      </Grid>
                    </Grid>
                    <Grid item xs={12}>
                      <MDBox p={2}>
                        <Canvas style={{height: "100%", height: "80vh", background: "#000000"}}>
                          <CameraController cameraLock={cameraLock}/>
                          <CoordinateSystem length={50} origin={[300, -300, -150]}/>
                          <ShadowLight x={-100} y={-100} z={-100} color={0xffffff} intensity={0.5}/>
                          <ShadowLight x={100} y={100} z={100} color={0xffffff} intensity={0.5}/>
                          <hemisphereLight args={[0xffffff, 0xffffff, 0.2]} color={0x3385ff} groundColor={0xffc880} position={[0, 100, 0]} />
                          <hemisphereLight args={[0xffffff, 0xffffff, 0.2]} color={0x3385ff} groundColor={0xffc880} position={[0, -100, 0]} />
                          <group matrixAutoUpdate={false} matrix={worldMatrix}>
                            {controlItems.map((item) => {
                              if (item.data && item.show) {
                                if (item.type === "STL") {
                                  return <Model key={item.filename} geometry={item.data} material={{
                                    color: item.color,
                                    specular: 0x111111,
                                    shininess: 200,
                                    opacity: 0.8
                                  }} matrix={item.matrix}></Model>
                                } else if (item.type === "Electrodes") {
                                  let matrix = computeElectrodePlacement(item.targetPt, item.entryPt);
                                  return <group key={item.filename}>
                                    {item.data.map((value, index) => {
                                      return <Model key={item.subname[index]} geometry={value} material={{
                                        color: item.subname[index].endsWith("shaft.stl") ? item.color : "#FFFFFF",
                                        specular: 0x111111,
                                        shininess: 200,
                                        opacity: item.opacity
                                      }} matrix={matrix}></Model>
                                    })}
                                  </group>
                                } else if (item.type === "sphere") {
                                  return item.data.map((arrayPoints, index) => {
                                    return <SphereObject key={item.filename} pointArray={arrayPoints} color={item.color} size={0.5} matrix={item.matrix}/>
                                  })
                                } else if (item.type === "points") {
                                  return item.data.map((arrayPoints, index) => {
                                    return <Tractography key={item.filename + index} pointArray={arrayPoints} color={item.color} linewidth={item.thickness} matrix={item.matrix}/>
                                  })
                                } else if (item.type === "tracts") {
                                  return item.data.map((arrayPoints, index) => {
                                    return <Tractography key={item.filename + index} pointArray={arrayPoints} color={item.color} linewidth={item.thickness} matrix={item.matrix}/>
                                  })
                                } else if (item.type === "volume") {
                                  return <VolumetricObject key={item.filename} data={item.data} matrix={worldMatrix} cameraLock={cameraLock} />
                                }
                              }
                            })}
                          </group>
                          {controlItems.map((item) => {
                            if (item.data && item.show) {
                              if (item.type === "GLB") {
                                if (item.isMesh) {
                                  return <primitive key={item.filename} object={item.data} scale={1} />
                                }
                              }
                            }
                          })}
                        </Canvas>
                      </MDBox>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
            </Grid>
          </MDBox>

          <Dialog open={showRecordingList} onClose={() => setShowRecordingList(false)} 
            PaperProps={{ sx: {minWidth: { xs: "100vw", sm: 900 }} }}
          >
            <ImagingSelect images={availableItems} onSelectRecording={(recordings) => {
              addModels(availableItems.filter((a) => recordings.includes(a.Id)))
            }} onClose={() => setShowRecordingList(false)} />
          </Dialog>

          <Dialog open={editTargetEntry.show} onClose={() => setEditTargetEntry({...editTargetEntry, show: false})}>
            <MDBox px={2} pt={2}>
              <MDTypography variant="h5">
                {"Edit Electrode Target/Entry Points"}
              </MDTypography>
              <MDTypography variant="p" fontSize={24}>
                {editTargetEntry.item}
              </MDTypography>
            </MDBox>
            <DialogContent style={{minWidth: 500}} >
              <MDBox style={{display: "flex", flexDirection: "row"}}>
                <TextField
                  variant="standard"
                  margin="dense"
                  value={editTargetEntry.name}
                  onChange={(event) => setEditTargetEntry((editTargetEntry) => {
                    editTargetEntry.name = event.target.value;
                    return {...editTargetEntry};
                  })}
                  label={"Electrode Name"} type={"text"}
                  autoComplete={"off"}
                  fullWidth
                />
              </MDBox>
              <MDBox style={{display: "flex", flexDirection: "row"}}>
                {editTargetEntry.targetPoint.map((value, index) => {
                  let coordinate = ["x", "y", "z"];
                  return <TextField
                    variant="standard"
                    margin="dense"
                    value={editTargetEntry.targetPoint[index]}
                    onChange={(event) => setEditTargetEntry((editTargetEntry) => {
                      editTargetEntry.targetPoint[index] = event.target.value;
                      return {...editTargetEntry};
                    })}
                    label={"Target Position " + coordinate[index] + ":"} type={"number"}
                    autoComplete={"off"}
                    fullWidth
                  />
                })}
              </MDBox>

              <MDBox style={{display: "flex", flexDirection: "row"}}>
                {editTargetEntry.entryPoint.map((value, index) => {
                  let coordinate = ["x", "y", "z"];
                  return <TextField
                    variant="standard"
                    margin="dense"
                    value={editTargetEntry.entryPoint[index]}
                    onChange={(event) => setEditTargetEntry((editTargetEntry) => {
                      editTargetEntry.entryPoint[index] = event.target.value;
                      return {...editTargetEntry};
                    })}
                    label={"Entry Position " + coordinate[index] + ":"} type={"number"}
                    autoComplete={"off"}
                    fullWidth
                  />
                })}
              </MDBox>
            </DialogContent>
            <MDBox px={2} py={2} style={{display: "flex", justifyContent: "flex-end"}}>
              <MDButton variant={"gradient"} color={"secondary"} onClick={() => setEditTargetEntry({...editTargetEntry, show: false})}>
                {"Cancel"}
              </MDButton>
              <MDButton variant={"gradient"} color={"success"} style={{marginLeft: 10}} onClick={updateTargetPoints}>
                {"Update"}
              </MDButton>
            </MDBox>
          </Dialog>
        </MDBox>
      </DatabaseLayout>
    </>
  );
}

export default ImageVisualization;
