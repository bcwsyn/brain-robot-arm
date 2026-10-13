// Bounded read-only coordinate probe. No ROS or arm interfaces, no flash writes.
#include <OpenNI.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <iomanip>
#include <array>

int main(int argc, char **argv) {
  using nlohmann::json;
  json out{{"camera_only",true},{"arm_interfaces_used",false}};
  auto rc = openni::OpenNI::initialize();
  if(rc != openni::STATUS_OK) {std::cerr << openni::OpenNI::getExtendedError(); return 2;}
  {
    openni::Device device;
    rc=device.open(openni::ANY_DEVICE);
    if(rc != openni::STATUS_OK) {std::cerr << openni::OpenNI::getExtendedError(); return 3;}
    out["uri"]=device.getDeviceInfo().getUri();
    OBCameraParams params{}; int size=sizeof(params);
    const auto param_rc=device.getProperty(openni::OBEXTENSION_ID_CAM_PARAMS,&params,&size);
    out["params_status"]=int(param_rc);
    if(param_rc==openni::STATUS_OK) {
      out["depth_intrinsics"]=std::vector<float>(params.l_intr_p,params.l_intr_p+4);
      out["color_intrinsics"]=std::vector<float>(params.r_intr_p,params.r_intr_p+4);
      out["rotation"]=std::vector<float>(params.r2l_r,params.r2l_r+9);
      out["translation_mm"]=std::vector<float>(params.r2l_t,params.r2l_t+3);
    }
    openni::VideoStream depth;
    rc=depth.create(device,openni::SENSOR_DEPTH);
    if(rc != openni::STATUS_OK) {std::cerr << openni::OpenNI::getExtendedError(); return 4;}
    openni::VideoMode selected;
    bool found=false;
    const auto &modes=depth.getSensorInfo().getSupportedVideoModes();
    for(int i=0;i<modes.getSize();++i) {
      if(modes[i].getResolutionX()==640 && modes[i].getResolutionY()==400 &&
         modes[i].getPixelFormat()==openni::PIXEL_FORMAT_DEPTH_1_MM && modes[i].getFps()==30) {
        selected=modes[i]; found=true; break;
      }
    }
    if(!found) {std::cerr << "Expected native 640x400 1mm profile unavailable"; return 5;}
    rc=depth.setVideoMode(selected);
    if(rc != openni::STATUS_OK) {std::cerr << "Native video mode rejected"; return 6;}
    out["depth_profile"]={640,400,30};
    const bool start_stream=argc==2 && std::string(argv[1])=="--stream";
    out["stream_started"]=start_stream;
    if(start_stream) {
      const auto start_rc=depth.start(); out["stream_start_status"]=int(start_rc);
      if(start_rc!=openni::STATUS_OK) {std::cerr << openni::OpenNI::getExtendedError(); return 7;}
      int changed=-1; openni::VideoStream *stream=&depth;
      const auto wait_rc=openni::OpenNI::waitForAnyStream(&stream,1,&changed,2000);
      out["frame_wait_status"]=int(wait_rc);
      if(wait_rc==openni::STATUS_OK) {
        openni::VideoFrameRef frame; const auto read_rc=depth.readFrame(&frame);
        out["frame_read_status"]=int(read_rc);
        if(read_rc==openni::STATUS_OK) {out["frame_index"]=frame.getFrameIndex();}
      }
    }
    out["points"]=json::array();
    // Known numeric coordinates only, not asserted to be cube observations.
    for(const auto &p:std::array<std::array<int,3>,6>{{
        {{326,200,186}},{{320,368,186}},{{350,340,186}},
        {{160,350,188}},{{326,200,350}},{{250,250,300}}}}) {
      int cx=-9999,cy=-9999,dx=-9999,dy=-9999;
      const auto s=openni::CoordinateConverter::convertD2CCoordinateByIntrinsic(
        depth,p[0],p[1],p[2],&cx,&cy);
      const std::string error=openni::OpenNI::getExtendedError();
      const auto back=openni::CoordinateConverter::convertC2DCoordinateByIntrinsic(
        depth,cx,cy,p[2],&dx,&dy);
      out["points"].push_back({{"depth_pixel_mm",p},{"d2c_status",int(s)},
        {"color_pixel",{cx,cy}},{"d2c_error",error},{"c2d_status",int(back)},{"depth_roundtrip_pixel",{dx,dy}}});
    }
    if(start_stream) {depth.stop();}
    depth.destroy();
    device.close();
  }
  openni::OpenNI::shutdown();
  std::cout << std::setprecision(17) << out.dump(2) << '\n';
  return 0;
}
