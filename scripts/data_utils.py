from torch.utils.data import Dataset, DataLoader
from scipy import signal
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

def distance(p1, p2):
    return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def interp(p1, p2, t):
    return (1.0 - t) * p1 + t * p2

def get_dir(p1, p2):
    return (p2 - p1) / distance(p1, p2)

def bezier_interp(p0, p1, p2, p3, t):
    """Returns the bezier point at the time t."""
    M = np.array([[-1, 3, -3, 1], \
                [3, -6, 3, 0], \
                [-3, 3, 0, 0], \
                [1, 0, 0, 0]])
    G = np.vstack((p0, p1, p2, p3))
    T = np.array([[t*t*t, t*t, t, 1]])
    result = T@M@G
    return result[0]
    
def resample(xs, ys, N):
    xy = np.array([xs, ys]).T
    avg_dist = 0.0
    for i in range(len(xs)-1):
        d = distance(xy[i], xy[i+1])
        avg_dist += d
    avg_dist /= (N-1)

    new_points = []
    last_point = xy[0]
    progress = 0.0
    from_origin = 0.0
    for i in range(1, len(xs)):
        this_point = xy[i]
        this_distance = distance(this_point, last_point)
        from_origin += this_distance
        while progress + avg_dist < from_origin:
            ratio = 1.0 - (from_origin - progress) / this_distance
            new_points.append(interp(last_point, this_point, ratio))
            progress += avg_dist
        last_point = this_point.copy()

    return np.array(new_points)

def normalizeControl(xs, ys, ts, dist=None):
    # input: arry of (x, y) of smoothened control signal
    # return: equidistant (x, y) points, and tangent vectors at each point

    # determine average displacement and how many samples
    N = len(xs)
    assert N == len(ys)
    xy = np.array([xs, ys]).T
    if dist:
        avg_dist = dist
    else:
        avg_dist = 0.0
        for i in range(N-1):
            d = distance(xy[i], xy[i+1])
            avg_dist += d
        avg_dist /= (N-1)
    
    new_points = []
    new_times = []
    last_point = xy[0]
    last_time = ts[0]
    progress = 0.0
    from_origin = 0.0
    for i in range(1, N):
        this_point = xy[i]
        this_time = ts[i]
        this_distance = distance(this_point, last_point)
        from_origin += this_distance
        while progress + avg_dist < from_origin:
            ratio = 1.0 - (from_origin - progress) / this_distance
            new_points.append(interp(last_point, this_point, ratio))
            new_times.append(interp(last_time, this_time, ratio))
            progress += avg_dist
        last_point = this_point.copy()
        last_time = this_time

    L = len(new_points)
    tangents = []
    tangents.append(get_dir(new_points[0], new_points[1]))
    for i in range(1, L-1):
        tangents.append(get_dir(new_points[i-1], new_points[i+1]))
    tangents.append(get_dir(new_points[L-2], new_points[L-1]))

    return np.array(new_points), np.array(new_times), np.array(tangents)


def straigtenStroke(xs, ys, ts, control, control_times, tangents):
    target_time = 0.0
    stroke_idx = 0
    new_points = []

    stroke_xy = np.array((xs, ys)).T

    # find the closest stroke point to the start
    #dist = 10000.0
    #for i in range(len(xs)):
    #    d = distance(stroke_xy[i], control[0])
    #    if d < dist:
    #        dist = d
    #        #stroke_idx = i

    for i in range(len(control_times)):
        t = control_times[i]
        while ts[stroke_idx+1] < t:
            stroke_idx += 1
        if stroke_idx < 2:
            p0 = stroke_xy[stroke_idx]
            p1 = stroke_xy[stroke_idx]
            p2 = stroke_xy[stroke_idx]
            p3 = stroke_xy[stroke_idx + 1]
        elif stroke_idx == len(xs) - 1:
            p0 = stroke_xy[stroke_idx - 2]
            p1 = stroke_xy[stroke_idx - 1]
            p2 = stroke_xy[stroke_idx]
            p3 = stroke_xy[stroke_idx]
        else:
            p0 = stroke_xy[stroke_idx - 2]
            p1 = stroke_xy[stroke_idx - 1]
            p2 = stroke_xy[stroke_idx]
            p3 = stroke_xy[stroke_idx + 1]
            
        p = bezier_interp(p0, p1, p2, p3, (t - ts[stroke_idx]) / (ts[stroke_idx+1] - ts[stroke_idx]))
        p0 = control[i]
        dp = p - p0
        tangent = tangents[i]
        bitangent = np.array([-tangent[1], tangent[0]])
        dx = np.dot(dp, tangent)
        dy = np.dot(dp, bitangent)
        new_points.append(np.array([dx, dy]))

    return np.array(new_points)


def kz(series, window, iterations):
    """KZ filter implementation
    series is a pandas series
    window is the filter window m in the units of the data (m = 2q+1)
    iterations is the number of times the moving average is evaluated
    """
    z = pd.Series(series)
    for i in range(iterations):
        z = z.rolling(window, min_periods=1, center=True).mean()
        #z = pd.rolling_mean(z, window=window, min_periods=1, center=True)
    return z.to_numpy()

def slice1d(arr, L, interval=1): # slice a numpy array
    assert len(arr) > L
    result = []
    for i in range(0, len(arr) - L + 1, interval):
        result.append(arr[i:i+L])
    return result


def scale01(arr):
    max_val = arr.max()
    min_val = arr.min()
    arr = (arr - min_val) / (max_val - min_val)
    return arr

def rotate(xs, ys, theta):
    mat = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    result = np.dot(mat, np.vstack((np.array(xs), np.array(ys))))
    return result[0, :], result[1, :]

class FromNpy(Dataset):
    def __init__(self, filename):
        self.data = np.load(filename)

    def __len__(self):
        return self.data.shape[0]

    def __getitem__(self, idx):
        return self.data[idx]


class MixData(Dataset):
    def __init__(self, filename, generated_files, n_styles=7, seg_len=100, window=100, smooth_iterations=5, cutoff=0, delta=1.5, interval=1):
        style_data = {}
        self.n_styles = n_styles
        encode = np.eye(n_styles).astype(np.float32)
        self.style_encode = {}
        self.original_data = {}
        for i in range(n_styles):
            self.style_encode[i] = encode[i]
            style_data[i] = [[],[]]
            self.original_data[i] = [[],[], [], []]
        self.cutoff = cutoff
        if isinstance(cutoff, tuple):
            cutoff_left = cutoff[0]
            cutoff_right = cutoff[1]
        else:
            cutoff_left = cutoff
            cutoff_right = cutoff
        self.delta = delta
        with open(filename) as f:
            f.readline() # discard first line
            while True:
                line = f.readline()
                if not line:
                    break
                index, style, pointx, pointy, controlx, controly = line.split(",")
                style = int(style)
                point_times = np.array([i for i in range(len(pointx))])
                pointx = np.array([float(i) for i in pointx.split(' ')], dtype=np.float32)
                pointy = np.array([float(i) for i in pointy.split(' ')], dtype=np.float32)
                assert len(pointx) == len(pointy)
                if len(pointx) < window + 2:
                    continue
                # smooth with KZ filter
                smooth_times = kz(point_times, window, smooth_iterations)
                smoothx = kz(pointx, window, smooth_iterations)
                smoothy = kz(pointy, window, smooth_iterations)
                self.original_data[style][0].append(pointx)
                self.original_data[style][1].append(pointy)
                self.original_data[style][2].append(smoothx)
                self.original_data[style][3].append(smoothy)
                control, control_times, tangents = normalizeControl(smoothx, smoothy, smooth_times, delta)
                stroke_delta = straigtenStroke(pointx, pointy, point_times, control, control_times, tangents)
                dx = stroke_delta[:,0]
                dy = stroke_delta[:,1]
                L = len(dx)
                x_sliced = slice1d(dx.tolist()[cutoff_left : L-cutoff_right], seg_len, interval)
                y_sliced = slice1d(dy.tolist()[cutoff_left : L-cutoff_right], seg_len, interval)
                for i in range(len(x_sliced)):
                    style_data[style][0].append(x_sliced[i])
                    style_data[style][1].append(y_sliced[i])
        style = 5 # hard code!!
        window=10
        smooth_iterations=10
        delta=1.1
        for fname in generated_files:
            x, y = [], []
            with open(fname) as f:
                for line in f.readlines():
                    x1, y1 = line.split(',')
                    x.append(float(x1))
                    y.append(float(y1))
            pointx = np.cumsum(x)
            pointy = np.cumsum(y)
            point_times = np.array([i for i in range(len(pointx))])
            smooth_times = kz(point_times, window, smooth_iterations)
            smoothx = kz(pointx, window, smooth_iterations)
            smoothy = kz(pointy, window, smooth_iterations)
            self.original_data[style][0].append(pointx)
            self.original_data[style][1].append(pointy)
            self.original_data[style][2].append(smoothx)
            self.original_data[style][3].append(smoothy)
            control, control_times, tangents = normalizeControl(smoothx, smoothy, smooth_times, delta)
            stroke_delta = straigtenStroke(pointx, pointy, point_times, control, control_times, tangents)
            dx = stroke_delta[:,0]
            dy = stroke_delta[:,1]
            L = len(dx)
            x_sliced = slice1d(dx.tolist()[cutoff_left : L-cutoff_right], seg_len, interval)
            y_sliced = slice1d(dy.tolist()[cutoff_left : L-cutoff_right], seg_len, interval)
            for i in range(len(x_sliced)):
                style_data[style][0].append(x_sliced[i])
                style_data[style][1].append(y_sliced[i])
            style += 1

        result = {}
        for i in range(n_styles):
            result[i] = np.transpose(np.array(style_data[i], dtype=np.float32), (1, 0, 2))
            # transpose to N, C, L
        self.data_len = {}
        for i in range(n_styles):
            self.data_len[i] = result[i].shape[0]
        for i in range(n_styles):
            print ("Loaded %s segments of style %s" % (self.data_len[i], i))
            print ("Shape: (%s, %s, %s)" % result[i].shape)
            
        self.data = result

    def __len__(self):
        s = 0
        for i in range(self.n_styles):
            s += self.data_len[i]
        return s

    def __getitem__(self, idx):
        start = 0
        for i in range(self.n_styles):
            if idx < start + self.data_len[i]:
                style = i
                break
            start += self.data_len[i]
        return self.data[style][idx - start], self.style_encode[style]

    def visualize_d(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        plt.plot(data[0, :], label="dx")
        plt.plot(data[1, :], label="dy")
        plt.legend()

    def visualize(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        N = len(data[0,:])
        control_x = np.array([i for i in range(N)]) * self.delta
        x = control_x + data[0, :]
        y = data[1,:]
        plt.scatter(x, y, s=1, label="original")
        plt.legend()

    def visualize_original(self, style, idx):
        x = self.original_data[style][0][idx]
        y = self.original_data[style][1][idx]
        cx = self.original_data[style][2][idx]
        cy = self.original_data[style][3][idx]
        plt.scatter(x, y, s=1, label="original")
        plt.scatter(cx, cy, s=1, label="smooth")
        plt.legend()
        print("Length = ", len(x))

class ControlRelative(Dataset):
    def __init__(self, filename, n_styles = 5, seg_len=100, window=100, smooth_iterations=5, cutoff=0, delta=1.5, interval=1, small_data=False):
        style_data = {}
        self.n_styles = n_styles
        encode = np.eye(n_styles).astype(np.float32)
        self.style_encode = {}
        self.original_data = {}
        for i in range(n_styles):
            self.style_encode[i] = encode[i]
            style_data[i] = [[],[]]
            self.original_data[i] = [[],[], [], []]
        self.cutoff = cutoff
        if isinstance(cutoff, tuple):
            cutoff_left = cutoff[0]
            cutoff_right = cutoff[1]
        else:
            cutoff_left = cutoff
            cutoff_right = cutoff
        self.delta = delta
        with open(filename) as f:
            # format:
            # id, style, pointx, pointy, controlx, controly
            f.readline() # discard first line
            while True:
                line = f.readline()
                if not line:
                    break
                index, style, pointx, pointy, controlx, controly = line.split(",")
                style = int(style)

                if small_data:
                    for i in range(4):
                        f.readline()

                point_times = np.array([i for i in range(len(pointx))])
                pointx = np.array([float(i) for i in pointx.split(' ')], dtype=np.float32)
                pointy = np.array([float(i) for i in pointy.split(' ')], dtype=np.float32)

                assert len(pointx) == len(pointy)

                if len(pointx) < window + 2:
                    continue

                    
                # smooth with KZ filter
                smooth_times = kz(point_times, window, smooth_iterations)
                smoothx = kz(pointx, window, smooth_iterations)
                smoothy = kz(pointy, window, smooth_iterations)
                
                self.original_data[style][0].append(pointx)
                self.original_data[style][1].append(pointy)
                self.original_data[style][2].append(smoothx)
                self.original_data[style][3].append(smoothy)

                control, control_times, tangents = normalizeControl(smoothx, smoothy, smooth_times, delta)
    
                stroke_delta = straigtenStroke(pointx, pointy, point_times, control, control_times, tangents)
                dx = stroke_delta[:,0]
                dy = stroke_delta[:,1]

                L = len(dx)
                x_sliced = slice1d(dx.tolist()[cutoff_left : L-cutoff_right], seg_len, interval)
                y_sliced = slice1d(dy.tolist()[cutoff_left : L-cutoff_right], seg_len, interval)

                for i in range(len(x_sliced)):
                    style_data[style][0].append(x_sliced[i])
                    style_data[style][1].append(y_sliced[i])

        result = {}
        for i in range(n_styles):
            result[i] = np.transpose(np.array(style_data[i], dtype=np.float32), (1, 0, 2))
            # transpose to N, C, L
        self.data_len = {}
        for i in range(n_styles):
            self.data_len[i] = result[i].shape[0]
        for i in range(n_styles):
            print ("Loaded %s segments of style %s" % (self.data_len[i], i))
            print ("Shape: (%s, %s, %s)" % result[i].shape)
            
        self.data = result

    def __len__(self):
        s = 0
        for i in range(self.n_styles):
            s += self.data_len[i]
        return s

    def __getitem__(self, idx):
        start = 0
        for i in range(self.n_styles):
            if idx < start + self.data_len[i]:
                style = i
                break
            start += self.data_len[i]
        return self.data[style][idx - start], self.style_encode[style]

    def visualize_d(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        plt.plot(data[0, :], label="dx")
        plt.plot(data[1, :], label="dy")
        plt.legend()

    def visualize(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        N = len(data[0,:])
        #tangents = np.vstack((np.ones(N), np.zeros(N))).T
        #bitangents = np.vstack((np.zeros(N), np.ones(N))).T
        control_x = np.array([i for i in range(N)]) * self.delta
        x = control_x + data[0, :]
        y = data[1,:]
        #cx = np.cumsum(data[2,:])
        #cy = np.cumsum(data[3,:])
        plt.scatter(x, y, s=1, label="original")
        #plt.scatter(cx, cy, s=1, label="smooth")
        plt.legend()

    def visualize_original(self, style, idx):
        x = self.original_data[style][0][idx]
        y = self.original_data[style][1][idx]
        cx = self.original_data[style][2][idx]
        cy = self.original_data[style][3][idx]
        plt.scatter(x, y, s=1, label="original")
        plt.scatter(cx, cy, s=1, label="smooth")
        plt.legend()
        print("Length = ", len(x))


class Guided(Dataset):
    def __init__(self, filename, n_styles = 5, seg_len=100, window=100, smooth_iterations=5, cutoff=0):
        style_data = {}
        self.n_styles = n_styles
        encode = np.eye(n_styles).astype(np.float32)
        self.style_encode = {}
        self.original_data = {}
        for i in range(n_styles):
            self.style_encode[i] = encode[i]
            style_data[i] = [[],[],[],[]]
            self.original_data[i] = [[],[],[],[]]
        self.cutoff = cutoff

        with open(filename) as f:
            # format:
            # id, style, pointx, pointy, controlx, controly
            f.readline() # discard first line
            while True:
                line = f.readline()
                if not line:
                    break
                index, style, pointx, pointy, controlx, controly = line.split(",")
                style = int(style)

                pointx = np.array([float(i) for i in pointx.split(' ')], dtype=np.float32)
                pointy = np.array([float(i) for i in pointy.split(' ')], dtype=np.float32)

                assert len(pointx) == len(pointy)

                if len(pointx) < window + 2:
                    continue
                    
                # smooth with KZ filter
                smoothx = kz(pointx, window, smooth_iterations)
                smoothy = kz(pointy, window, smooth_iterations)

                self.original_data[style][0].append(pointx)
                self.original_data[style][1].append(pointy)
                self.original_data[style][2].append(smoothx)
                self.original_data[style][3].append(smoothy)

                dx = pointx[1:] - pointx[:-1]
                dy = pointy[1:] - pointy[:-1]
                dcx = smoothx[1:] - smoothx[:-1]
                dcy = smoothy[1:] - smoothy[:-1]
                L = len(dx)

                x_sliced = slice1d(dx.tolist()[self.cutoff : L-self.cutoff], seg_len)
                y_sliced = slice1d(dy.tolist()[self.cutoff : L-self.cutoff], seg_len)
                cx_sliced = slice1d(dcx.tolist()[self.cutoff : L-self.cutoff], seg_len)
                cy_sliced = slice1d(dcy.tolist()[self.cutoff : L-self.cutoff], seg_len)
                for i in range(len(x_sliced)):
                    theta = np.random.uniform(0.0, 2*np.pi)
                    #theta = 0.0
                    new_x, new_y = rotate(x_sliced[i], y_sliced[i], theta)
                    new_cx, new_cy = rotate(cx_sliced[i], cy_sliced[i], theta)
                    style_data[style][0].append(new_x)
                    style_data[style][1].append(new_y)
                    style_data[style][2].append(new_cx)
                    style_data[style][3].append(new_cy)
        
        result = {}
        for i in range(n_styles):
            result[i] = np.transpose(np.array(style_data[i], dtype=np.float32), (1, 0, 2))
            # transpose to N, C, L
        self.data_len = {}
        for i in range(n_styles):
            self.data_len[i] = result[i].shape[0]
        for i in range(n_styles):
            print ("Loaded %s segments of style %s" % (self.data_len[i], i))
            print ("Shape: (%s, %s, %s)" % result[i].shape)
            
        self.data = result

    def __len__(self):
        s = 0
        for i in range(self.n_styles):
            s += self.data_len[i]
        return s

    def __getitem__(self, idx):
        start = 0
        for i in range(self.n_styles):
            if idx < start + self.data_len[i]:
                style = i
                break
            start += self.data_len[i]
        return self.data[style][idx - start], self.style_encode[style]

    def visualize_d(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        plt.plot(data[0, :], label="dx")
        plt.plot(data[1, :], label="dy")
        plt.plot(data[2, :], label="dcx")
        plt.plot(data[3, :], label="dcy")
        plt.legend()

    def visualize(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        x = np.cumsum(data[0,:])
        y = np.cumsum(data[1,:])
        cx = np.cumsum(data[2,:])
        cy = np.cumsum(data[3,:])
        plt.scatter(x, y, s=1, label="original")
        plt.scatter(cx, cy, s=1, label="smooth")
        plt.legend()

    def visualize_original(self, style, idx):
        x = self.original_data[style][0][idx]
        y = self.original_data[style][1][idx]
        cx = self.original_data[style][2][idx]
        cy = self.original_data[style][3][idx]
        plt.scatter(x, y, s=1, label="original")
        plt.scatter(cx, cy, s=1, label="smooth")
        plt.legend()

class SmoothCurve(Dataset):
    def __init__(self, filename, seg_len=100, window=100, smooth_iterations=5):
        style_data = {}
        n_styles = 3
        self.n_styles = n_styles
        self.style_encode = {
            0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            1: np.array([0.0, 1.0, 0.0], dtype=np.float32),
            2: np.array([0.0, 0.0, 1.0], dtype=np.float32)
        }
        for i in range(n_styles):
            style_data[i] = [[],[],[],[]]

        with open(filename) as f:
            # format:
            # id, style, pointx, pointy, controlx, controly
            f.readline() # discard first line
            while True:
                line = f.readline()
                if not line:
                    break
                index, style, pointx, pointy, controlx, controly = line.split(",")
                style = int(style)

                pointx = np.array([float(i) for i in pointx.split(' ')], dtype=np.float32)
                pointy = np.array([float(i) for i in pointy.split(' ')], dtype=np.float32)

                assert len(pointx) == len(pointy)

                if len(pointx) < window + 2:
                    continue
                    
                # smooth with KZ filter
                smoothx = kz(pointx, window, smooth_iterations)
                smoothy = kz(pointy, window, smooth_iterations)

                dx = pointx[1:] - pointx[:-1]
                dy = pointy[1:] - pointy[:-1]
                dcx = smoothx[1:] - smoothx[:-1]
                dcy = smoothy[1:] - smoothy[:-1]

                x_sliced = slice1d(dx.tolist(), seg_len)
                y_sliced = slice1d(dy.tolist(), seg_len)
                cx_sliced = slice1d(dcx.tolist(), seg_len)
                cy_sliced = slice1d(dcy.tolist(), seg_len)
                for i in range(len(x_sliced)):
                    theta = np.random.uniform(0.0, 2*np.pi)
                    new_x, new_y = rotate(x_sliced[i], y_sliced[i], theta)
                    new_cx, new_cy = rotate(cx_sliced[i], cy_sliced[i], theta)
                    style_data[style][0].append(new_x)
                    style_data[style][1].append(new_y)
                    style_data[style][2].append(new_cx)
                    style_data[style][3].append(new_cy)
        
        result = {}
        for i in range(n_styles):
            result[i] = np.transpose(np.array(style_data[i], dtype=np.float32), (1, 0, 2))
            # transpose to N, C, L
        self.data_len = {}
        for i in range(n_styles):
            self.data_len[i] = result[i].shape[0]
        for i in range(n_styles):
            print ("Loaded %s segments of style %s" % (self.data_len[i], i))
            print ("Shape: (%s, %s, %s)" % result[i].shape)
            
        self.data = result

    def __len__(self):
        s = 0
        for i in range(self.n_styles):
            s += self.data_len[i]
        return s

    def __getitem__(self, idx):
        if idx < self.data_len[0]:
            style = 0
            start = 0
        elif idx < self.data_len[0] + self.data_len[1]:
            style = 1
            start = self.data_len[0]
        else:
            style = 2
            start = self.data_len[0] + self.data_len[1]
        return self.data[style][idx - start], self.style_encode[style]

    def visualize_d(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        plt.plot(data[0, :], label="dx")
        plt.plot(data[1, :], label="dy")
        plt.plot(data[2, :], label="dcx")
        plt.plot(data[3, :], label="dcy")
        plt.legend()

    def visualize(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        x = np.cumsum(data[0,:])
        y = np.cumsum(data[1,:])
        cx = np.cumsum(data[2,:])
        cy = np.cumsum(data[3,:])
        plt.scatter(x, y, s=1, label="original")
        plt.scatter(cx, cy, s=1, label="smooth")
        plt.legend()

class DisplaceControl(Dataset):
    def __init__(self, filename, seg_len=100):
        # 3 styles
        style_data = {}
        n_styles = 3
        self.n_styles = n_styles
        self.style_encode = {
            0: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            1: np.array([0.0, 1.0, 0.0], dtype=np.float32),
            2: np.array([0.0, 0.0, 1.0], dtype=np.float32)
        }
        for i in range(n_styles):
            style_data[i] = [[],[],[],[]]

        with open(filename) as f:
            # format:
            # id, style, pointx, pointy, controlx, controly
            f.readline() # discard first line
            while True:
                line = f.readline()
                if not line:
                    break
                index, style, pointx, pointy, controlx, controly = line.split(",")
                style = int(style)

                pointx = np.array([float(i) for i in pointx.split(' ')], dtype=np.float32)
                pointy = np.array([float(i) for i in pointy.split(' ')], dtype=np.float32)
                controlx = np.array([float(i) for i in controlx.split(' ')], dtype=np.float32)
                controly = np.array([float(i) for i in controly.split(' ')], dtype=np.float32)
                assert len(pointx) == len(controly)
                assert len(pointy) == len(controlx)
                dx = pointx[1:] - pointx[:-1]
                dy = pointy[1:] - pointy[:-1]
                dcx = controlx[1:] - controlx[:-1]
                dcy = controly[1:] - controly[:-1]

                if (len(dx) < 2*seg_len):
                    continue

                x_sliced = slice1d(dx.tolist(), seg_len)
                y_sliced = slice1d(dy.tolist(), seg_len)
                cx_sliced = slice1d(dcx.tolist(), seg_len)
                cy_sliced = slice1d(dcy.tolist(), seg_len)
                for i in range(len(x_sliced)):
                    style_data[style][0].append(x_sliced[i])
                    style_data[style][1].append(y_sliced[i])
                    style_data[style][2].append(cx_sliced[i])
                    style_data[style][3].append(cy_sliced[i])

                
        result = {}
        for i in range(n_styles):
            result[i] = np.transpose(np.array(style_data[i], dtype=np.float32), (1, 0, 2))
            # transpose to N, C, L
        self.data_len = {}
        for i in range(n_styles):
            self.data_len[i] = result[i].shape[0]
        if self.data_len[0] != self.data_len[1]  or self.data_len[0] != self.data_len[2] :
            print ("Warning: styles have different numbers of data")
        for i in range(n_styles):
            print ("Loaded %s segments of style %s" % (self.data_len[i], i))

        self.data = result
        #print(result[0].shape)
        #print(result[0])


    def __len__(self):
        s = 0
        for i in range(self.n_styles):
            s += self.data_len[i]
        return s

    def __getitem__(self, idx):
        if idx < self.data_len[0]:
            style = 0
            start = 0
        elif idx < self.data_len[0] + self.data_len[1]:
            style = 1
            start = self.data_len[0]
        else:
            style = 2
            start = self.data_len[0] + self.data_len[1]
        return self.data[style][idx - start, :2, :], self.style_encode[style]

    def visualize_d(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        plt.plot(data[0, :], label="dx")
        plt.plot(data[1, :], label="dy")
        plt.legend()

    def visualize(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        x = np.cumsum(data[0,:])
        y = np.cumsum(data[1,:])
        plt.plot(x, y)

class SimulateDisplace(Dataset):
    def __init__(self):
        L = 2000
        tmax = 500.0
        t = np.linspace(0, tmax, L)

        # style A
        yt = 0.8 * np.sin(t) + np.random.normal(0.0, 0.002, size=L)
        xt = np.linspace(0.0, tmax, L) + np.random.normal(0.0, 0.005, size=L) # velocity ~ 1.0
        
        self.original_a = np.array([xt[1:] - xt[:-1], yt[1:] - yt[:-1]], dtype=np.float32)
        
        # style B
        vt = 0.5 * np.ones_like(t)
        n_cycles = np.floor(t / np.pi / 2.0)
        step = np.where(t / np.pi / 2.0 - n_cycles > 0.5, 1.0, 0.0)
        vt += step
        dt = tmax / L
        xt = [vt[0] * dt]
        for i in range(1, L):
            xt.append(xt[i-1] + vt[i]*dt)
        xt = np.array(xt) + np.random.normal(0.0, 0.002, size=L)
        yt = 0.6 * signal.sawtooth(t, 0.5) + np.random.normal(0.0, 0.002, size=L)

        self.original_b = np.array([xt[1:] - xt[:-1], yt[1:] - yt[:-1]], dtype=np.float32)
        
        # style C
        yt = 0.57 * np.sin(0.8 * t) + 0.7 * np.sin(1.9 * t) + np.random.normal(0.0, 0.002, size=L)
        vt = np.abs(signal.sawtooth(t, 0.75)) + 0.5
        xt = [vt[0] * dt]
        for i in range(1, L):
            xt.append(xt[i-1] + vt[i]*dt)
        xt = np.array(xt) + np.random.normal(0.0, 0.002, size=L)

        self.original_c = np.array([xt[1:] - xt[:-1], yt[1:] - yt[:-1]], dtype=np.float32)

        seg = 100

        self.data_a = []
        self.data_b = []
        self.data_c = []
        for i in range(L -1 - seg + 1):
            self.data_a.append(self.original_a[:, i:i+seg])
            self.data_b.append(self.original_b[:, i:i+seg])
            self.data_c.append(self.original_c[:, i:i+seg])
            
        self.style_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        self.style_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.style_c = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    def __len__(self):
        return len(self.data_a) * 3

    def __getitem__(self, idx):
        s = idx % 3
        i = idx // 3
        if s == 0:
            data = self.data_a
            style = self.style_a
        elif s == 1:
            data = self.data_b
            style = self.style_b
        else:
            data = self.data_c
            style = self.style_c
        return data[i], style

    def visualize_d(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        plt.plot(data[0, :], label="dx")
        plt.plot(data[1, :], label="dy")
        plt.legend()

    def visualize(self, idx):
        data, style = self[idx]
        print("Encoded style: ", style)
        x = np.cumsum(data[0,:])
        y = np.cumsum(data[1,:])
        plt.plot(x, y)


class SameData(Dataset):
    def __init__(self):
        L = 2200
        t = np.linspace(0, 400, L)
        self.original_a = np.array([0.8 * np.sin(3.0 * t), 0.3 * np.ones(L)], dtype=np.float32)
        self.original_a[0] += np.random.normal(0.0, 0.02, size=L)
        self.original_a[1] += np.random.normal(0.0, 0.01, size=L)

        self.original_b = np.array([0.7 * np.sin(3.0 * t) + 1.0 + 0.55 * np.cos(1.7 * t), 0.2 * np.ones(L)], dtype=np.float32)
        self.original_b[0] += np.random.normal(0.0, 0.05, size=L)
        self.original_b[1] += np.random.normal(0.0, 0.01, size=L)
        
        self.original_c = np.array([0.57 * np.sin(2.0 * t), 0.2 * np.ones(L)], dtype=np.float32)

        def scale01(arr):
            max_val = arr.max()
            min_val = arr.min()
            arr = (arr - min_val) / (max_val - min_val)
            return arr
        
        seg = 100
        self.original_a[0] = scale01(self.original_a[0])
        self.original_b[0] = scale01(self.original_b[0])
        self.original_c[0] = scale01(self.original_c[0])

        self.data_a = []
        self.data_b = []
        self.data_c = []
        for i in range(500):
            a = np.zeros_like(self.original_a[:, :seg])
            a[0, :] = self.original_a[0, :seg] + np.random.normal(0.0, 0.02, size=seg)
            a[1, :] = self.original_a[1, :seg] + np.random.normal(0.0, 0.02, size=seg)
            self.data_a.append(np.array(a))

            b = np.zeros_like(self.original_b[:, :seg])
            b[0, :] = self.original_b[0, :seg] + np.random.normal(0.0, 0.02, size=seg)
            b[1, :] = self.original_b[1, :seg] + np.random.normal(0.0, 0.02, size=seg)
            self.data_b.append(np.array(b))

            c = np.zeros_like(self.original_c[:, :seg])
            c[0, :] = self.original_c[0, :seg] + np.random.normal(0.0, 0.02, size=seg)
            c[1, :] = self.original_c[1, :seg] + np.random.normal(0.0, 0.02, size=seg)
            self.data_c.append(np.array(c))
        #for i in range(L - 100 + 1):
        #    self.data_a.append(self.original_a[:, i:i+100])
            
        self.style_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        self.style_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.style_c = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    #def __len__(self):
    #    return len(self.data_a)

    #def __getitem__(self, idx):
    #    return self.data_a[idx], self.style_a
    
    def __len__(self):
        return len(self.data_a) * 3

    def __getitem__(self, idx):
        s = idx % 3
        i = idx // 3
        if s == 0:
            data = self.data_a
            style = self.style_a
        elif s == 1:
            data = self.data_b
            style = self.style_b
        else:
            data = self.data_c
            style = self.style_c
        return data[i], style

class Data1D(Dataset):
    def __init__(self):
        self.n_styles = 3
        L = 1100
        t = np.linspace(0, 200, L)
        self.original_a = np.array([0.8 * np.sin(3.0 * t), 0.3 * np.ones(L)], dtype=np.float32)
        self.original_a[0] += np.random.normal(0.0, 0.02, size=L)
        self.original_a[1] += np.random.normal(0.0, 0.01, size=L)
        
        self.original_b = np.array([0.7 * np.sin(3.0 * t) + 1.0 + 0.55 * np.cos(1.7 * t), 0.2 * np.ones(L)], dtype=np.float32)
        self.original_b[0] += np.random.normal(0.0, 0.05, size=L)
        self.original_b[1] += np.random.normal(0.0, 0.01, size=L)
        
        self.original_c = np.array([0.57 * np.sin(2.0 * t), 0.2 * np.ones(L)], dtype=np.float32)
        self.original_c[0] += np.random.normal(0.0, 0.05, size=L)
        self.original_c[1] += np.random.normal(0.0, 0.03, size=L)
        
        def scale01(arr):
            max_val = arr.max()
            min_val = arr.min()
            arr = (arr - min_val) / (max_val - min_val)
            return arr
        
        self.original_a[0] = scale01(self.original_a[0])
        self.original_b[0] = scale01(self.original_b[0])
        self.original_c[0] = scale01(self.original_c[0])
        
        self.data_a = []
        self.data_b = []
        self.data_c = []
        for i in range(L - 100 + 1):
            self.data_a.append(self.original_a[:, i:i+100])
            self.data_b.append(self.original_b[:, i:i+100])
            self.data_c.append(self.original_c[:, i:i+100])
            
        self.style_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        self.style_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.style_c = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        
    
    def __len__(self):
        return len(self.data_a) * 3

    def __getitem__(self, idx):
        s = idx % 3
        i = idx // 3
        if s == 0:
            data = self.data_a
            style = self.style_a
        elif s == 1:
            data = self.data_b
            style = self.style_b
        else:
            data = self.data_c
            style = self.style_c
        return data[i], style
        
    def visualize(self, idx):
        data, style = self[idx]
        length = data.shape[1]
        t = 0.0
        x = []
        y = []
        for i in range(length):
            x.append(t)
            t += data[1, i]
            y.append(data[0,i])
        plt.plot(x, y)
        
    def visualize_full(self, s):
        if s == 0:
            data = self.original_a
        elif s == 1:
            data = self.original_b
        else:
            data = self.original_c
        length = data.shape[1]
        t = 0.0
        x = []
        y = []
        for i in range(length):
            x.append(t)
            t += data[1, i]
            y.append(data[0,i])
        plt.plot(x, y)