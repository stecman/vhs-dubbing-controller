var url = '/hls/stream.m3u8';
var element = document.getElementById('video');
var player = null;

function toggleMute() {
    element.muted = !element.muted;

    element.classList.toggle('muted');
}

function toggleFullscreen() {
    if (element.requestFullscreen) {
        element.requestFullscreen()
    } else if (element.webkitRequestFullscreen) {
        element.webkitRequestFullscreen();
    } else if (element.mozRequestFullScreen) {
        element.mozRequestFullScreen();
    } else if (element.msRequestFullscreen) {
        element.msRequestFullscreen()
    } else {
        console.error('Fullscreen API is not supported by this browser');
    }
}

function seekBackwards() {
    element.currentTime = element.currentTime - 5;
    player._isLive = false;
    document.getElementById('video_controls').classList.remove('live');
}

function seekToLive() {
    element.currentTime = element.duration - 0.5;
    player._isLive = true;
    document.getElementById('video_controls').classList.add('live');
}

function VideoTouchControl(node) {
    this.video = node;
    this._touchPosition = null;
    this._timeout = null;

    node.addEventListener('touchstart', this._handleTouchStart.bind(this));
}

VideoTouchControl.prototype = {
    singleTap: function(callback) {
        this._singleTapCallback = callback;
        return this;
    },

    doubleTap: function(callback) {
        this._doubleTapCallback = callback;
        return this;
    },

    _handleTouchStart: function(e) {
        e.preventDefault();

        const existingTouchCount = e.touches.length - e.changedTouches.length;

        if (existingTouchCount == 0) {
            const touch = e.changedTouches[0];
            const pos = { x: touch.pageX, y: touch.pageY };

            clearTimeout(this._timeout);

            if (this._touchPosition && this._isNear(pos, this._touchPosition)) {
                this._touchPosition = null;

                if (this._doubleTapCallback) {
                    this._doubleTapCallback();
                }
            } else {
                // New touch or outside of distance tolerance for double tap
                this._touchPosition = pos;
                this._timeout = setTimeout(this._doubleTapTimeout.bind(this), 200);
            }

        }
    },

    _doubleTapTimeout: function() {
        if (this._touchPosition != null) {
            this._touchPosition = null;

            if (this._singleTapCallback) {
                this._singleTapCallback();
            }
        }
    },

    _isNear: function(a, b) {
        const kTolerance = 25;

        return (Math.abs(a.x - b.x) < kTolerance) &&
               (Math.abs(a.y - b.y) < kTolerance);
    }
};

// Bind video tapping actions
const touchControls = new VideoTouchControl(element);
touchControls.singleTap(toggleMute);
touchControls.doubleTap(toggleFullscreen);

// Bind Controls
document.getElementById('unmute_message').addEventListener('touchstart', toggleMute);
document.getElementById('fullscreen').addEventListener('click', toggleFullscreen);

// The seek buttons are disabled as a buffer of video to skip to isn't consistently
// available. These may also confuse the operator into thinking it affects the recorder.
//
// document.getElementById('seek_back').addEventListener('click', seekBackwards);
// document.getElementById('resume_live').addEventListener('click', seekToLive);

function start()  {
    element.style.display = 'block';

    if (Hls.isSupported()) {
        player = new Hls();
        player.attachMedia(element);
        player.on(Hls.Events.MEDIA_ATTACHED, function() {
            console.log('bound hls to DOM element');
            player.loadSource(url);
            player.on(Hls.Events.MANIFEST_PARSED, function(event, data) {
                console.log('manifest loaded with ' + data.levels.length + ' quality level(s)');
                element.play();
            });
        });

        // Flag to check if the user has seeked backwards
        player._isLive = true;
        document.getElementById('video_controls').classList.add('live');

        player._lastError = null;

        player.on(Hls.Events.ERROR, function (event, data) {
            console.error(data);

            if (data.fatal) {
                switch(data.type) {
                    case Hls.ErrorTypes.NETWORK_ERROR:
                        // try to recover network error
                        console.log("fatal network error encountered, try to recover");
                        player.startLoad();
                        break;
                    case Hls.ErrorTypes.MEDIA_ERROR:
                        console.log("fatal media error encountered, try to recover");
                        player.recoverMediaError();
                        break;
                    default:
                        // cannot recover
                        player.destroy();
                        break;
                }
            }
        });
    }
    // hls.js is not supported on platforms that do not have Media Source
    // Extensions (MSE) enabled.
    //
    // When the browser has built-in HLS support (check using `canPlayType`),
    // we can provide an HLS manifest (i.e. .m3u8 URL) directly to the video
    // element through the `src` property. This is using the built-in support
    // of the plain video element, without using hls.js.
    //
    // Note: it would be more normal to wait on the 'canplay' event below however
    // on Safari (where you are most likely to find built-in HLS support) the
    // video.src URL must be on the user-driven white-list before a 'canplay'
    // event will be emitted; the last video event that can be reliably
    // listened-for when the URL is not on the white-list is 'loadedmetadata'.
    else if (element.canPlayType('application/vnd.apple.mpegurl') !== '') {
        element.src = url;
        element.addEventListener('loadedmetadata', function() {
            element.play();
        });
    } else {
        throw new Error('hls not supported');
    }
};

// Monitor playback distance from live:
// Adjust the seek if this player is too far behind
setInterval(function() {
    if (player === null) {
        return;
    }

    if ((element.duration - element.currentTime) > 3) {
        console.warn('Adjusting playback to live: too far behind');

        element.currentTime = element.duration - 0.5;
    }
}, 500);

function stop() {
    player.destroy();
    player = null;
};

function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function updateMetadata(data) {
    const node = document.getElementById('ffmpeg_data');

    if (data) {
        node.classList.remove('hidden');

        document.getElementById('meta_frame').innerText = numberWithCommas(parseInt(data['frame'], 10));
        document.getElementById('meta_time').innerText = data['time'];
        document.getElementById('meta_bitrate').innerText = data['bitrate'];
        document.getElementById('meta_size').innerText = data['size'];
    } else {
        node.classList.add('hidden');
    }
}

function updateStatus(data) {
    const status = data.recorder;
    const isStreamReady = data.streamReady;

    // Push some state into data attributes for CSS to use
    const kStatusAttribute = 'data-status';
    const kHasStreamAttribute = 'data-ready';

    const statusNode = document.getElementById('recorder_state');

    if (statusNode.getAttribute(kStatusAttribute) != status) {
        statusNode.setAttribute(kStatusAttribute, status);
    }

    const videoContainer = document.getElementById('video_wrapper');

    if (videoContainer.getAttribute(kStatusAttribute) != status) {
        videoContainer.setAttribute(kStatusAttribute, status);
    }

    if (videoContainer.getAttribute(kHasStreamAttribute) != isStreamReady) {
        videoContainer.setAttribute(kHasStreamAttribute, isStreamReady ? 1 : 0);
    }

    // Hide the controls when not streaming
    const controlsContainer = document.getElementById('video_controls');
    const displayState = player === null ? 'none' : '';

    if (controlsContainer.style.display !== displayState) {
        controlsContainer.style.display = displayState;
    }
}

function updatePlayer(data) {
    if (player === null) {
        if (data.recorder == 'preview' || data.recorder == 'recording') {
            if (data.streamReady) {
                start();
            }
        }
    } else {
        if (data.recorder == 'idle') {
            stop();
        }
    }
}

// Open a websocket to interact with the server
const ws = new WebSocket(`ws://${window.location.host}/socket`);
ws.onopen = function() {
    ws.send("Hello, world");
};

ws.onmessage = function (evt) {
    const msg = JSON.parse(evt.data);

    switch (msg.type) {
        case 'state':
            recorder_status = msg.data.recorder;

            updateStatus(msg.data);
            updateMetadata(msg.data.ffmpeg);
            updatePlayer(msg.data);
            break;
    }

    // console.log(msg)
};