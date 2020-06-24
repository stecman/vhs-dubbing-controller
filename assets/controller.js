var url = '/hls/stream.m3u8';
var element = document.getElementById('video');
var player = null;

var autoplay = !window.location.search.includes('novideo');
var userDidInteract = false;

function toggleMute() {
    element.muted = !element.muted;
    element.classList.toggle('muted');
}

function unmute() {
    element.muted = false;
    element.classList.remove('muted');
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

function abortRecording() {
    const reallyStop = prompt('Really stop this recording?\n\nPlease only do this if something has gone wrong and you have stopped the tape to intervene. The recording will be kept.\n\nType \'stop\' below to confirm');

    if (reallyStop && reallyStop.trim().toLowerCase() == 'stop') {
        ws.send('stop');
    }
}

function startRecording() {
    userDidInteract = true;
    const durationSeconds = durationManager.getDuration();

    if (durationSeconds < 1) {
        alert('Please enter a valid duration');
        document.getElementById('duration_input').focus();
        return;
    }

    ws.send('record:' + durationSeconds);
}

function incrementTape() {
    ws.send('increment');
}

function toggleHelpMode(e) {
    e.preventDefault();
    document.body.classList.toggle('help-mode');
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

// Bind video controls
document.getElementById('unmute_message').addEventListener('touchstart', toggleMute);
document.getElementById('fullscreen').addEventListener('click', toggleFullscreen);

// The seek buttons are disabled as a buffer of video to skip to isn't consistently
// available. These may also confuse the operator into thinking it affects the recorder.
//
// document.getElementById('seek_back').addEventListener('click', seekBackwards);
// document.getElementById('resume_live').addEventListener('click', seekToLive);

// Bind other buttons
document.getElementById('button_new_tape').addEventListener('click', incrementTape);
document.getElementById('button_stop_recording').addEventListener('click', abortRecording);
document.getElementById('button_record').addEventListener('click', startRecording);

document.getElementById('help_link').addEventListener('click', toggleHelpMode);
document.getElementById('help_close_link').addEventListener('click', toggleHelpMode);

// Set up masked input for easy duration entry
const durationManager = (function(){
    var durationSeconds = 0;

    const inputNode = document.getElementById('duration_input');
    const outputNode = document.getElementById('duration_output');

    var lastValue = null;

    function handleUpdate(e) {
        const raw = inputNode.value.toString()
            .replace(/[^0-9]*/g, '') // Only permit numerals
            .replace(/^0+/, ''); // Avoid the user adding leading zeros (fills the field silently)

        // Drop any non-numeric characters that got into the input
        if (raw !== inputNode.value.toString()) {
            inputNode.value = raw;
        }

        // Only handle when the value has changed
        if (lastValue == raw) {
            return;
        } else {
            lastValue = raw;
        }

        // Block having more than four digits
        if (raw.length > 4 && e) {
            e.preventDefault();
            e.stopPropagation();
            inputNode.value = raw.substr(0, 4);
            return false;
        }

        // Collect groups of two digits from the right-hand side
        // The smallest unit is always first in the output list (so, [MM, H] or [M] or [MM] etc)
        var parts = [];

        for (var i = 0; i < raw.length; i += 2) {
            // Factor for substr returning at index 0 when passed an negative index past the start of the string
            const length = Math.min(raw.length - i, 2);
            parts.push(raw.substr((-i)-2, length));
        }

        const suffixes = ['m', 'h'];
        const secondMultipliers = [60, 60*60];

        var output = [];

        durationSeconds = 0;

        for (var i = 0; i < suffixes.length; i++) {
            output.push('<span class="duration-control__suffix">' + suffixes[i] + '</span>');

            if (parts[i]) {
                output.push(parts[i]);

                if (parts[i].length === 1) {
                    output.push('0');
                }

                durationSeconds += secondMultipliers[i] * parseInt(parts[i]);

            } else {
                output.push('00');
            }

            if (i < (suffixes.length - 1)) {
                output.push('<span> ');
            }
        }

        outputNode.innerHTML = output.reverse().join('');
    }

    function handleFocus(e) {
        outputNode.classList.add('focused');
        handleUpdate();
    }

    function handleBlur(e) {
        outputNode.classList.remove('focused');
    }

    function handleSubmit(e) {
        e.preventDefault();
        inputNode.blur();
    }

    function setDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        seconds -= (hours * 3600);

        console.log(hours)

        const minutes = Math.floor(seconds / 60);
        seconds -= minutes * 60;

        console.log(minutes)

        durationSeconds = seconds;
        inputNode.value = hours.toString() + (minutes < 10 ? '0' : '') + minutes.toString();
        handleUpdate();
    }

    function getDuration() {
        return durationSeconds;
    }

    inputNode.addEventListener('keypress', handleUpdate);
    inputNode.addEventListener('change', handleUpdate);
    inputNode.addEventListener('keyup', handleUpdate);
    inputNode.addEventListener('keydown', handleUpdate);
    inputNode.addEventListener('focus', handleFocus);
    inputNode.addEventListener('blur', handleBlur);
    inputNode.form.addEventListener('submit', handleSubmit);
    handleUpdate();

    return {
        setDuration: setDuration,
        getDuration: getDuration,
    }
})();

function start()  {
    element.style.display = 'block';

    if (Hls.isSupported()) {
        player = new Hls();
        player.attachMedia(element);
        player.on(Hls.Events.MEDIA_ATTACHED, function() {
            player.loadSource(url);
            player.on(Hls.Events.MANIFEST_PARSED, function(event, data) {
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

function stop() {
    if (player !== null) {
        player.destroy();
        player = null;
    }
}

function formatSeconds(seconds) {
    const hours = Math.floor(seconds / 3600);
    seconds -= (hours * 3600);

    const minutes = Math.floor(seconds / 60);
    seconds -= minutes * 60;

    return `${hours}h ${(minutes < 10 ? '0' : '')}${minutes}m`;
    handleUpdate();
}

function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function updateMetadata(data) {
    const node = document.getElementById('ffmpeg_data');

    if ((data.recorder == 'recording' || data.recorder == 'start-recording')) {
        document.getElementById('duration_display_readonly').innerText = formatSeconds(data.duration);

        if (data.ffmpeg) {
            node.classList.remove('hidden');

            document.getElementById('meta_frame').innerText = numberWithCommas(parseInt(data.ffmpeg['frame'], 10));
            document.getElementById('meta_time').innerText = data.ffmpeg['time'];
            document.getElementById('meta_bitrate').innerText = data.ffmpeg['bitrate'];
            document.getElementById('meta_size').innerText = data.ffmpeg['size'];
        } else {
            node.classList.add('hidden');
        }
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

var lastState = null;
function updatePlayer(data) {
    if (player === null) {
        if (data.recorder == 'preview' || data.recorder == 'recording') {
            if (data.streamReady && autoplay) {
                start();

                if (userDidInteract && data.recorder == 'recording') {
                    // Turn off mute to encourage monitoring audio
                    unmute();
                }
            }
        }
    } else {
        if ((!data.streamReady) || data.recorder == 'idle') {
            stop();
        }

        // Automatically start the preview again if a recording finishes while connecte
        if (data.recorder == 'idle') {
            ws.send('preview');
        }
    }

    // Get updated file info at each recorder state change
    if (lastState != data.recorder) {
        ws.send('fileinfo');
    }

    lastState = data.recorder;
}

function updateFileInfo(data) {
    const newTapeButton = document.getElementById('button_new_tape');
    const recordButton = document.getElementById('button_record');

    document.querySelectorAll('[data-archive-number]').forEach(node => {
        node.innerText = data.tape_number;
    });

    newTapeButton.disabled = data.recording_count < 1;

    if (newTapeButton.disabled) {
        recordButton.innerText = 'Start Recording';
    } else {
        recordButton.innerHTML = `Start Another Recording for ${data.tape_number}`;
    }
}

// Open a websocket to interact with the server
const ws = new WebSocket(`ws://${window.location.host}/socket`);
ws.onopen = function() {
    console.log('Connected');

    // Ask the server to send which tape file is active
    // This info isn't pushed automatically like the video info is
    ws.send('fileinfo');
};

ws.onclose = function() {
    console.log('Disconnected');
    stop();

    // Show the disconnect overlay
    // This either means the network changed or the server crashed
    document.getElementById('ws-failure').style.display = '';
};

ws.onmessage = function (evt) {
    const msg = JSON.parse(evt.data);

    switch (msg.type) {
        case 'state':
            recorder_status = msg.data.recorder;

            updateStatus(msg.data);
            updateMetadata(msg.data);
            updatePlayer(msg.data);
            break;

        case 'fileinfo':
            updateFileInfo(msg.data)
            break;
    }

    // console.log(msg)
};