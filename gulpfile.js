const { src, dest, watch } = require("gulp");
const if_ = require("gulp-if");
const sourcemaps = require("gulp-sourcemaps");
const sass = require("gulp-sass")(require("sass"));
const touch = require("gulp-touch-fd");

const isDev = !!process.env.DEBUG;

const build = () =>
  src("ckanext/datagovau/theme/dga.scss")
    .pipe(if_(isDev, sourcemaps.init()))
    .pipe(sass())
    .pipe(if_(isDev, sourcemaps.write()))
      .pipe(dest("ckanext/datagovau/assets/css"))
      .pipe(touch());

const watchSource = () =>
  watch(
    "ckanext/datagovau/theme/**/*.scss",
    { ignoreInitial: false },
    build
  );
exports.watch = watchSource;
exports.build = build;
