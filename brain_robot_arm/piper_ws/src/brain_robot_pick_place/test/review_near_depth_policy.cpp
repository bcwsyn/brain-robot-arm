// Offline-only bridge for recorded-image tests. No ROS, publishers or hardware
// interfaces. Each stdin row supplies factory calibration, a measured seed,
// model-predicted DEPTH point and evidence; argv[1] is the original RGB file.
#include <iostream>
#include <iomanip>
#include <opencv2/imgcodecs.hpp>
#include "brain_robot_pick_place/near_depth_tracking.hpp"
#include "brain_robot_pick_place/rgbd_shape_geometry.hpp"

int main(int argc, char ** argv)
{
  namespace br = brain_robot_pick_place;
  namespace nd = br::near_depth;
  if (argc != 2) {return 2;}
  const auto image = cv::imread(argv[1]);
  if (image.empty()) {return 3;}
  nd::Calibration c;
  nd::Seed seed;
  nd::Evidence e;
  std::array<double, 3> point{};
  br::ColorShapeCriteria criteria;
  int h1, h2, s, v, kernel_size;
  std::cin >> c.width >> c.height >> c.fx >> c.fy >> c.cx >> c.cy >> c.mirror;
  for (auto & x : c.rotation) {std::cin >> x;}
  for (auto & x : c.translation) {std::cin >> x;}
  std::cin >> seed.box.left >> seed.box.top >> seed.box.right >> seed.box.bottom
    >> seed.color_z >> seed.valid >> e.model_locked >> e.exact_image_tf
    >> e.fresh_six_axis_feedback >> e.image_age_s >> e.receipt_age_s
    >> e.seed_age_s >> e.camera_travel_m;
  for (auto & x : point) {std::cin >> x;}
  std::cin >> criteria.min_area >> criteria.max_area >> criteria.min_circularity
    >> criteria.min_rectangularity >> criteria.min_aspect >> criteria.max_aspect
    >> criteria.rotated >> h1 >> h2 >> s >> v >> kernel_size;
  if (!std::cin || kernel_size <= 0) {return 4;}
  cv::Mat hsv, mask;
  cv::cvtColor(image, hsv, cv::COLOR_BGR2HSV);
  cv::inRange(hsv, cv::Scalar(h1, s, v), cv::Scalar(h2, 255, 255), mask);
  const auto kernel = cv::getStructuringElement(cv::MORPH_ELLIPSE,
    cv::Size(kernel_size, kernel_size));
  cv::morphologyEx(mask, mask, cv::MORPH_OPEN, kernel);
  cv::morphologyEx(mask, mask, cv::MORPH_CLOSE, kernel);
  std::vector<std::vector<cv::Point>> contours;
  cv::findContours(mask, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
  cv::Rect selected;
  double best = 0;
  for (const auto & contour : contours) {
    double area = 0, rect = 0, aspect = 0;
    if (br::qualified_color_shape(contour, criteria, area, rect, aspect) && area > best) {
      selected = cv::boundingRect(contour); best = area;
    }
  }
  br::visual_grasp::Box box{};
  if (best > 0 && selected.x > 1 && selected.y > 1 &&
    selected.x + selected.width < image.cols - 1 &&
    selected.y + selected.height < image.rows - 1)
  {
    box = {double(selected.x) / image.cols, double(selected.y) / image.rows,
      double(selected.x + selected.width) / image.cols,
      double(selected.y + selected.height) / image.rows};
  }
  nd::Projection projection;
  const char * rejected = "PROJECTION_UNAVAILABLE";
  if (nd::Project(c, point, image.cols, image.rows, projection)) {
    std::array<double, 3> delta{};
    rejected = "INVALID_RGB_CORRECTION";
    if (nd::RgbResidual(c, point, box, image.cols, image.rows, delta)) {
      const double residual = std::hypot(std::hypot(delta[0], delta[1]), delta[2]);
      rejected = nd::PredictionRejection(seed, e, box, projection, .6, 30, .030,
        residual, .04);
    }
  }
  std::cout << std::setprecision(15) << (rejected ? rejected : "ASSOCIATED_LOCKED_RGB") << " "
    << box.left << " " << box.top << " " << box.right << " " << box.bottom << " "
    << projection.x << " " << projection.y << " " << projection.z << "\n";
  return 0;
}
