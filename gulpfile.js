const gulp = require("gulp");
const { resolve } = require("path");
const touch = require("gulp-touch-fd");
const if_ = require("gulp-if");
const sourcemaps = require("gulp-sourcemaps");
const less = require("gulp-less");
const cleanCss = require("gulp-cleancss");

const themeDir = resolve(__dirname, "ckanext/datagovau/theme");
const assetsDir = resolve(__dirname, "ckanext/datagovau/assets");

const isDev = () => !!process.env.DEBUG;

const build = () =>
  gulp
    .src(resolve(themeDir, "dga.less"))
    .pipe(if_(isDev, sourcemaps.init()))
    .pipe(less())
    .pipe(if_(() => !isDev(), cleanCss()))
    .pipe(if_(isDev, sourcemaps.write()))
    .pipe(gulp.dest(assetsDir))
    .pipe(touch());

const watch = () =>
  gulp.watch(resolve(themeDir, "*.less"), { ignoreInitial: false }, build);

exports.watch = watch;
exports.build = build;
