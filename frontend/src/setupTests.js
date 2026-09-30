import "@testing-library/jest-dom";

// jsdom has no media devices or canvas; tests install their own mocks per case.
HTMLMediaElement.prototype.play = function play() {
  return Promise.resolve();
};

beforeEach(() => {
  sessionStorage.clear();
});
