// Runs before every frontend test: adds extra test assertions and fakes browser features
// (video playback) that the test environment does not have.
import "@testing-library/jest-dom";

// jsdom has no media devices or canvas; tests install their own mocks per case.
HTMLMediaElement.prototype.play = function play() {
  return Promise.resolve();
};

beforeEach(() => {
  sessionStorage.clear();
});
