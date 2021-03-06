# Copyright 2020 Huy Le Nguyen (@usimarit) and Huy Phan (@pquochuy)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import argparse
from tensorflow_asr.utils import setup_environment, setup_strategy

setup_environment()
import tensorflow as tf

DEFAULT_YAML = os.path.join(os.path.abspath(os.path.dirname(__file__)), "config.yml")

parser = argparse.ArgumentParser(prog="SASEGAN")

parser.add_argument("--config", "-c", type=str, default=DEFAULT_YAML,
                    help="The file path of model configuration file")

parser.add_argument("--max_ckpts", type=int, default=10,
                    help="Max number of checkpoints to keep")

parser.add_argument("--tbs", type=int, default=None,
                    help="Train batch size per replicas")

parser.add_argument("--devices", type=int, nargs="*", default=[0],
                    help="Devices' ids to apply distributed training")

parser.add_argument("--mxp", default=False, action="store_true",
                    help="Enable mixed precision")

parser.add_argument("--nfx", default=False, action="store_true",
                    help="Choose numpy features extractor")

parser.add_argument("--cache", default=False, action="store_true",
                    help="Enable caching for dataset")

args = parser.parse_args()

tf.config.optimizer.set_experimental_options({"auto_mixed_precision": args.mxp})

strategy = setup_strategy(args.devices)

from sasegan.runners.trainer import SeganTrainer
from sasegan.datasets.train_dataset import SeganTrainDataset
from tensorflow_asr.configs.config import Config
from sasegan.models.segan import Generator, Discriminator
from sasegan.featurizers.speech_featurizer import NumpySpeechFeaturizer, TFSpeechFeaturizer

config = Config(args.config, learning=True)

speech_featurizer = NumpySpeechFeaturizer(config.speech_config) if args.nfx \
    else TFSpeechFeaturizer(config.speech_config)

dataset = SeganTrainDataset(
    stage="train", speech_featurizer=speech_featurizer,
    clean_dir=config.learning_config.dataset_config.train_paths["clean"],
    noisy_dir=config.learning_config.dataset_config.train_paths["noisy"],
    cache=args.cache, shuffle=True
)

segan_trainer = SeganTrainer(config.learning_config.running_config)

with segan_trainer.strategy.scope():
    generator = Generator(
        window_size=speech_featurizer.window_size,
        **config.model_config
    )
    generator._build()
    generator.summary(line_length=150)
    discriminator = Discriminator(
        window_size=speech_featurizer.window_size,
        **config.model_config
    )
    discriminator._build()
    discriminator.summary(line_length=100)

segan_trainer.compile(generator, discriminator,
                      config.learning_config.optimizer_config,
                      max_to_keep=args.max_ckpts)
segan_trainer.fit(train_dataset=dataset, train_bs=args.tbs)
