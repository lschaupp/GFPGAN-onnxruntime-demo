#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import argparse
import cv2
import numpy as np
import timeit
import onnxruntime

class GFPGANFaceAugment:
    def __init__(self, model_path, use_gpu = False):
        self.ort_session = onnxruntime.InferenceSession(model_path, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        self.net_input_name = self.ort_session.get_inputs()[0].name
        _,self.net_input_channels,self.net_input_height,self.net_input_width = self.ort_session.get_inputs()[0].shape
        self.net_output_count = len(self.ort_session.get_outputs())
        self.face_size = 512
        self.face_template = np.array([[192, 240], [319, 240], [257, 371]]) * (self.face_size / 512.0)
        self.upscale_factor = 2
        self.affine = False
        self.affine_matrix = None
    def pre_process(self, img):
        img = cv2.resize(img, (int(img.shape[1] / 2), int(img.shape[0] / 2)))
        img = cv2.resize(img, (self.face_size, self.face_size))
        img = img / 255.0
        img = img.astype('float32')
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img[:,:,0] = (img[:,:,0]-0.5)/0.5
        img[:,:,1] = (img[:,:,1]-0.5)/0.5
        img[:,:,2] = (img[:,:,2]-0.5)/0.5
        img = np.float32(img[np.newaxis,:,:,:])
        img = img.transpose(0, 3, 1, 2)
        return img
    def post_process(self, output, height, width):
        output = output.clip(-1,1)
        output = (output + 1) / 2
        output = output.transpose(1, 2, 0)
        output = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        output = (output * 255.0).round()
        if self.affine:
            inverse_affine = cv2.invertAffineTransform(self.affine_matrix)
            inverse_affine *= self.upscale_factor
            if self.upscale_factor > 1:
                extra_offset = 0.5 * self.upscale_factor
            else:
                extra_offset = 0
            inverse_affine[:, 2] += extra_offset
            inv_restored = cv2.warpAffine(output, inverse_affine, (width, height))
            mask = np.ones((self.face_size, self.face_size), dtype=np.float32)
            inv_mask = cv2.warpAffine(mask, inverse_affine, (width, height))
            inv_mask_erosion = cv2.erode(
                inv_mask, np.ones((int(2 * self.upscale_factor), int(2 * self.upscale_factor)), np.uint8))
            pasted_face = inv_mask_erosion[:, :, None] * inv_restored
            total_face_area = np.sum(inv_mask_erosion)
            # compute the fusion edge based on the area of face
            w_edge = int(total_face_area**0.5) // 20
            erosion_radius = w_edge * 2
            inv_mask_center = cv2.erode(inv_mask_erosion, np.ones((erosion_radius, erosion_radius), np.uint8))
            blur_size = w_edge * 2
            inv_soft_mask = cv2.GaussianBlur(inv_mask_center, (blur_size + 1, blur_size + 1), 0)
            inv_soft_mask = inv_soft_mask[:, :, None]
            output = pasted_face
        else:
            inv_soft_mask = np.ones((height, width, 1), dtype=np.float32)
            output = cv2.resize(output, (width, height))
        return output, inv_soft_mask

    def forward(self, img_1, img_2):
        height, width = img_1.shape[0], img_1.shape[1]
        height_2, width_2 = img_2.shape[0], img_2.shape[1]
        img_1 = self.pre_process(img_1)
        img_2 = self.pre_process(img_2)
        img = np.concatenate([img_1, img_2], axis=0)
        t = timeit.default_timer()
        ort_inputs = {self.ort_session.get_inputs()[0].name: img}
        ort_outs = self.ort_session.run(None, ort_inputs)
        output = ort_outs[0][0]
        output_2 = ort_outs[0][1]
        output, inv_soft_mask = self.post_process(output, height, width)
        output_2, _ = self.post_process(output_2, height_2, width_2)
        print('infer time:',timeit.default_timer()-t)  
        output = output.astype(np.uint8)
        output_2 = output_2.astype(np.uint8)
        return output, output_2, inv_soft_mask
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser("onnxruntime demo")
    parser.add_argument('--model_path', type=str, default=None, help='model path')
    parser.add_argument('--image_path', type=str, default=None, help='input image path')
    parser.add_argument('--image_path_2', type=str, default=None, help='input image path')
    parser.add_argument('--save_path', type=str, default="output.jpg", help='output image path')
    args = parser.parse_args()

    faceaugment = GFPGANFaceAugment(model_path=args.model_path)
    image = cv2.imread(args.image_path, 1)
    image_2 = cv2.imread(args.image_path_2, 1)
    output, output_2,  _ = faceaugment.forward(image, image_2)
    cv2.imwrite(args.save_path, output)
    cv2.imwrite("test.jpg", output_2)


# python demo_onnx.py --model_path GFPGANv1.4.onnx --image_path ./cropped_faces/Adele_crop.png


# python demo_onnx.py --model_path GFPGANv1.2.onnx --image_path ./cropped_faces/Adele_crop.png --save_path Adele_v2.jpg
# python demo_onnx.py --model_path GFPGANv1.2.onnx --image_path ./cropped_faces/Julia_Roberts_crop.png --save_path Julia_Roberts_v2.jpg
# python demo_onnx.py --model_path GFPGANv1.2.onnx --image_path ./cropped_faces/Justin_Timberlake_crop.png --save_path Justin_Timberlake_v2.jpg
# python demo_onnx.py --model_path GFPGANv1.2.onnx --image_path ./cropped_faces/Paris_Hilton_crop.png --save_path Paris_Hilton_v2.jpg
