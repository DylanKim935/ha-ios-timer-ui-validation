# Home Assistant native timer UI validation

A single manually dispatched GitHub Actions job captures the upstream Home Assistant
SwiftUI compact timer before and after a one-line alignment proposal, on an iPhone 17
simulator with iOS 27.0. It uses the upstream test suite and production views at
`2bca3df909a966686b14c5c552242a03fa28d064`.

The workflow records references, then runs the same tests in comparison mode for
each variant. It captures 4:11, 10:00, 9:59, 0:09 and the existing upstream cases.
The artifacts include native PNGs, source diffs, build logs and environment details.
Critical text, progress and expanded view images are checked for unintended changes.

This is native SwiftUI component rendering in an iOS Simulator. It is not a physical
iPhone test or a screenshot of SpringBoard's complete Dynamic Island. Visual review
of the generated images is still required. This is a validation workspace, not an
upstream issue or pull request. No Home Assistant server credentials, home configuration
or personal phone screenshots are included. No installable device build is distributed.

The upstream project is Apache-2.0 licensed: https://github.com/home-assistant/iOS.
The workflow and proposed patch were prepared with AI assistance.
