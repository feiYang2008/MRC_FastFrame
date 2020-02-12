import paddle
import paddle.fluid as fluid
import numpy as np
import time
from preprocess.preprocess import PreProcess as PrePro
from engine.train import TrainEngine as TrainEngine
from data.Dataset import Dataset
from preprocess.preprocess import PreProcess

from util.util_filepath import *
from util.util_parameter import UtilParameter as UParam
from util.util_logging import UtilLogging as ULog

ground_truth = (np.arange(2, 6).reshape(1, 4)/4)

def fake_sample_generator():
    for _ in range(1000):
        sample_x = np.random.random(size=(4,)).astype('float32')
        sample_y = np.dot(ground_truth, sample_x)
        yield sample_x, sample_y


if __name__ == "__main__":
    param = UParam()
    logger = ULog(param)
    # args = {
    #     "max_epoch": 100,
    #     "snapshot_frequency": 10,
    #     "early_stopping": True,
    #     "warm_up": False,
    #     "continue_train": True,
    #     "pretrained_model_path": "",
    #     "load_model_path": "/gs/home/lianghx/lhx/MRC/File_Directory/models/2020-02-09_15-50-34",
    #     "use_parallel": True,
    #     "use_gpu": True,
    #     "num_of_device": 2,
    #     "batch_size": 32,
    #     "base_learning_rate": 0.01,
    #     "learning_rate_strategy": "fixed",
    #     "start_learning_rate": 1e-04,
    #     "warm_up_step": 50,
    #     "end_learning_rate": 1e-04,
    #     "decay_step": 1000,
    #     "optimizer": "sgd",
    #     "adagrad_epsilon": 1e-06,
    #     "adagrad_accumulator_value": 0,
    #     "early_stopping_threshold": 0.03,
    #     "early_stopping_times": 5
    # }
    # datasets_path = args["datasets_path"]

    datasets = Dataset(logger)
 #   datasets.read_dataset(div_nums=[7, 2, 1])

    datasets.load_examples()
    trainset, validset, testset = datasets.get_split()  # 这三个函数要修改，split应该检查是否已分割
    # datasets.save_example()

    train_preprocess = PreProcess(logger, param.get_config("dataset"), examples=trainset)
    train_preprocess.prepare_batch_data()
    train_batch_reader = train_preprocess.batch_generator()
    print(len(next(train_batch_reader())))

    # valid_preprocess = PreProcess(logger, param.get_config("global"), examples=validset)
    # valid_batch_reader = valid_preprocess.batch_generator()
    # test_preprocess = PreProcess(trainset)
    # test_batch_reader = test_preprocess.batch_generator()
    #
    # # reader = fluid.io.batch(fake_sample_generator, batch_size=args["batch_size"])

    # train_engine = TrainEngine(train_batch_reader, valid_batch_reader, param.get_config("train"), logger)
    # t1 = time.time()
    # train_engine.train()
    # t2 = time.time()
    # print(t2-t1)
